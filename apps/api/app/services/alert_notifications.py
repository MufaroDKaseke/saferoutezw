"""Match published alerts to verified, consenting subscribers and deliver them.

* Only ``published`` alerts are considered; withdrawn alerts are never sent.
* Only ``active`` subscribers with an unwithdrawn consent receive anything; the check is repeated
  at send time, so someone who unsubscribes after being queued is skipped.
* Deliveries are keyed ``alert:<alert>:sub:<subscriber>:<channel>`` with a UNIQUE constraint and
  inserted with ON CONFLICT DO NOTHING, so worker retries never queue a duplicate.
* A delivery is claimed with ``FOR UPDATE SKIP LOCKED`` and its status recorded as sent / failed /
  unknown (never conflated). ``unknown`` is not retried, to avoid double sends.
* Alerts older than the subscriber's verification are never sent to them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    AlertSubscriber,
    BulletinVersion,
    PublicAlert,
    SubscriberDelivery,
    SubscriptionConsent,
    SubscriptionPreference,
)
from app.models.enums import AlertStatus
from app.models.subscription import DeliveryState, SubscriberStatus
from app.services.notifications import NotificationProvider, get_notification_provider
from app.services.subscriptions import decrypt_phone

log = logging.getLogger(__name__)

RECENT_ALERT_HOURS = 48  # never push alerts that are older than this
MAX_ALERT_TEXT = 300


@dataclass
class RunSummary:
    queued: int = 0
    sent: int = 0
    failed: int = 0
    unknown: int = 0
    skipped: int = 0


def matches(alert: PublicAlert, prefs: SubscriptionPreference) -> bool:
    if prefs.all_zimbabwe:
        return True
    if alert.province and alert.province in (prefs.provinces or []):
        return True
    road = (alert.road_name or "").lower()
    return bool(road) and any(c.lower() in road for c in (prefs.corridors or []))


def queue_deliveries(session: Session, now: datetime | None = None) -> int:
    """Create one queued delivery per matching (alert, subscriber). Idempotent."""
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=RECENT_ALERT_HOURS)
    alerts = session.scalars(
        select(PublicAlert).where(
            PublicAlert.status == AlertStatus.PUBLISHED.value, PublicAlert.published_at >= since
        )
    ).all()
    if not alerts:
        return 0
    subscribers = session.execute(
        select(AlertSubscriber, SubscriptionPreference)
        .join(SubscriptionPreference, SubscriptionPreference.subscriber_id == AlertSubscriber.id)
        .where(
            AlertSubscriber.status == SubscriberStatus.ACTIVE.value,
            AlertSubscriber.verified_at.is_not(None),
            exists().where(
                and_(
                    SubscriptionConsent.subscriber_id == AlertSubscriber.id,
                    SubscriptionConsent.withdrawn_at.is_(None),
                )
            ),
        )
    ).all()
    created = 0
    for alert in alerts:
        assert alert.published_at is not None
        for subscriber, prefs in subscribers:
            if subscriber.verified_at and alert.published_at < subscriber.verified_at:
                continue
            if not matches(alert, prefs):
                continue
            statement = (
                insert(SubscriberDelivery)
                .values(
                    public_alert_id=alert.id,
                    subscriber_id=subscriber.id,
                    channel=subscriber.channel,
                    idempotency_key=f"alert:{alert.id}:sub:{subscriber.id}:{subscriber.channel}",
                )
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(SubscriberDelivery.id)
            )
            # RETURNING yields a row only when a delivery was really inserted (not a conflict).
            created += 1 if session.execute(statement).first() is not None else 0
    session.commit()
    return created


def _message(session: Session, alert: PublicAlert) -> str:
    version = session.get(BulletinVersion, alert.bulletin_version_id)
    headline = (version.headline if version else "Road safety alert").strip()
    where = ", ".join(p for p in (alert.road_name, alert.province) if p)
    text = f"SafeRouteZW: {headline}"
    if where:
        text += f" ({where})"
    text = text[: MAX_ALERT_TEXT - 40].rstrip()
    return f"{text}. Details: /public/alerts/{alert.id}. Reply STOP to unsubscribe."


def deliver_due(
    session: Session,
    settings: Settings,
    now: datetime | None = None,
    provider_for=None,
) -> RunSummary:
    """Send due queued deliveries once. ``provider_for(channel)`` lets tests inject a provider."""
    now = now or datetime.now(UTC)
    provider_for = provider_for or (lambda channel: get_notification_provider(settings, channel))
    summary = RunSummary()
    ids = session.scalars(
        select(SubscriberDelivery.id)
        .where(
            SubscriberDelivery.status == DeliveryState.QUEUED.value,
            or_(SubscriberDelivery.next_attempt_at.is_(None), SubscriberDelivery.next_attempt_at <= now),
        )
        .order_by(SubscriberDelivery.created_at)
        .limit(500)
    ).all()
    for delivery_id in ids:
        delivery = session.scalar(
            select(SubscriberDelivery)
            .where(SubscriberDelivery.id == delivery_id, SubscriberDelivery.status == DeliveryState.QUEUED.value)
            .with_for_update(skip_locked=True)
        )
        if delivery is None:
            continue
        alert = session.get(PublicAlert, delivery.public_alert_id)
        subscriber = session.get(AlertSubscriber, delivery.subscriber_id)
        still_consenting = subscriber is not None and subscriber.status == SubscriberStatus.ACTIVE.value
        if alert is None or alert.status != AlertStatus.PUBLISHED.value or not still_consenting:
            delivery.status = DeliveryState.FAILED.value
            delivery.last_error = "skipped: alert withdrawn or subscriber no longer active"
            delivery.updated_at = now
            summary.skipped += 1
            session.commit()
            continue
        provider: NotificationProvider = provider_for(delivery.channel)
        delivery.attempts += 1
        delivery.provider_name = provider.name
        result = provider.send_alert(
            decrypt_phone(settings, subscriber.phone_ciphertext),
            _message(session, alert),
            idempotency_key=delivery.idempotency_key,
        )
        delivery.updated_at = now
        delivery.provider_reference = result.provider_reference
        if result.status == "sent":
            delivery.status = DeliveryState.SENT.value
            delivery.last_error = None
            summary.sent += 1
        elif result.status == "unknown":
            delivery.status = DeliveryState.UNKNOWN.value
            delivery.last_error = result.error
            summary.unknown += 1
        else:
            delivery.last_error = result.error
            if delivery.attempts >= settings.notification_max_attempts:
                delivery.status = DeliveryState.FAILED.value
                summary.failed += 1
            else:
                delivery.next_attempt_at = now + timedelta(minutes=2**delivery.attempts)
                summary.failed += 1  # this attempt failed; it stays queued for a retry
        session.commit()
    return summary


def apply_delivery_receipt(session: Session, provider_reference: str, delivered: bool) -> bool:
    """Record a provider delivery receipt (called by a verified provider callback)."""
    delivery = session.scalar(
        select(SubscriberDelivery).where(SubscriberDelivery.provider_reference == provider_reference)
    )
    if delivery is None:
        return False
    delivery.status = DeliveryState.DELIVERED.value if delivered else DeliveryState.FAILED.value
    delivery.updated_at = datetime.now(UTC)
    session.commit()
    return True


def run_once(session: Session, settings: Settings, provider_for=None) -> RunSummary:
    queued = queue_deliveries(session)
    summary = deliver_due(session, settings, provider_for=provider_for)
    summary.queued = queued
    return summary
