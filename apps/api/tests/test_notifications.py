"""Alert matching and delivery: published-only, consent-respecting, idempotent. Mock provider only."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    AlertSubscriber,
    SubscriberDelivery,
    SubscriptionConsent,
    SubscriptionPreference,
)
from app.services import alert_notifications as svc
from app.services import subscriptions as subs
from app.services.notifications.mock import MockNotificationProvider
from public_helpers import make_published_alert, make_settings

pytestmark = pytest.mark.usefixtures("migrated_engine")


def make_subscriber(session, settings, phone, *, status="active", provinces=("Mashonaland East",),
                    all_zimbabwe=False, corridors=(), channel="sms", consent=True):
    subscriber = AlertSubscriber(
        phone_ciphertext=subs.encrypt_phone(settings, phone),
        phone_digest=subs.keyed_digest(settings, f"phone:{phone}"),
        channel=channel,
        status=status,
        verified_at=datetime.now(UTC) - timedelta(hours=1) if status != "pending" else None,
    )
    session.add(subscriber)
    session.flush()
    session.add(SubscriptionPreference(
        subscriber_id=subscriber.id, all_zimbabwe=all_zimbabwe, provinces=list(provinces), corridors=list(corridors)
    ))
    if consent:
        session.add(SubscriptionConsent(
            subscriber_id=subscriber.id, consent_text_version="2026-11-v1", channel=channel,
            withdrawn_at=None if status == "active" else datetime.now(UTC),
        ))
    session.commit()
    return subscriber


def run(session, settings, provider):
    return svc.run_once(session, settings, provider_for=lambda channel: provider)


def deliveries(session):
    return session.scalars(select(SubscriberDelivery)).all()


def test_matching_by_province_corridor_and_all_zimbabwe(session):
    settings = make_settings()
    make_published_alert(session)  # Mashonaland East, road "A3 Harare-Mutare"
    make_subscriber(session, settings, "+263771000001")  # province match
    make_subscriber(session, settings, "+263771000002", provinces=("Bulawayo",))  # no match
    make_subscriber(session, settings, "+263771000003", provinces=(), corridors=("A3",))  # corridor match
    make_subscriber(session, settings, "+263771000004", provinces=(), all_zimbabwe=True)
    provider = MockNotificationProvider()
    summary = run(session, settings, provider)
    assert summary.queued == 3 and summary.sent == 3
    assert sorted(m.to_e164 for m in provider.messages) == ["+263771000001", "+263771000003", "+263771000004"]
    assert all(d.status == "sent" and d.provider_name == "mock" for d in deliveries(session))


def test_pending_unsubscribed_and_withdrawn_consent_never_receive(session):
    settings = make_settings()
    make_published_alert(session)
    make_subscriber(session, settings, "+263771000011", status="pending")
    make_subscriber(session, settings, "+263771000012", status="unsubscribed")
    make_subscriber(session, settings, "+263771000013", consent=False)
    provider = MockNotificationProvider()
    assert run(session, settings, provider).queued == 0 and provider.messages == []


def test_only_published_alerts_are_notified(session):
    settings = make_settings()
    alert, incident, _ = make_published_alert(session)
    alert.status = "ready"
    session.commit()
    make_subscriber(session, settings, "+263771000021")
    provider = MockNotificationProvider()
    assert run(session, settings, provider).queued == 0 and provider.messages == []


def test_running_twice_never_duplicates_a_delivery(session):
    settings = make_settings()
    make_published_alert(session)
    make_subscriber(session, settings, "+263771000031")
    provider = MockNotificationProvider()
    run(session, settings, provider)
    again = run(session, settings, provider)
    assert again.queued == 0 and again.sent == 0
    assert len(deliveries(session)) == 1 and len(provider.messages) == 1


def test_unsubscribing_after_queueing_stops_the_send(session):
    settings = make_settings()
    make_published_alert(session)
    subscriber = make_subscriber(session, settings, "+263771000041")
    assert svc.queue_deliveries(session) == 1
    subs.unsubscribe(session, subscriber)
    provider = MockNotificationProvider()
    summary = svc.deliver_due(session, settings, provider_for=lambda c: provider)
    assert summary.skipped == 1 and provider.messages == []
    assert deliveries(session)[0].status == "failed" and "no longer active" in deliveries(session)[0].last_error


def test_withdrawn_alerts_are_not_sent(session):
    settings = make_settings()
    alert, _, _ = make_published_alert(session)
    make_subscriber(session, settings, "+263771000051")
    svc.queue_deliveries(session)
    alert.status = "withdrawn"
    session.commit()
    provider = MockNotificationProvider()
    assert svc.deliver_due(session, settings, provider_for=lambda c: provider).skipped == 1
    assert provider.messages == []


def test_provider_failures_are_recorded_and_retried_with_backoff(session):
    settings = make_settings(notification_max_attempts=2)
    make_published_alert(session)
    make_subscriber(session, settings, "+263771000061")
    provider = MockNotificationProvider(fail_next=1)
    first = run(session, settings, provider)
    delivery = deliveries(session)[0]
    assert first.failed == 1 and delivery.status == "queued" and delivery.attempts == 1
    assert delivery.last_error and delivery.next_attempt_at > datetime.now(UTC)
    later = datetime.now(UTC) + timedelta(hours=1)
    assert svc.deliver_due(session, settings, now=later, provider_for=lambda c: provider).sent == 1
    assert deliveries(session)[0].status == "sent" and deliveries(session)[0].attempts == 2


def test_permanent_failure_and_unknown_status_are_tracked_separately(session):
    settings = make_settings(notification_max_attempts=1)
    make_published_alert(session)
    make_published_alert(session, headline="[SYNTHETIC] Second alert")
    make_subscriber(session, settings, "+263771000071")
    provider = MockNotificationProvider(fail_next=1, unknown_next=1)
    summary = run(session, settings, provider)
    assert summary.failed == 1 and summary.unknown == 1
    assert sorted(d.status for d in deliveries(session)) == ["failed", "unknown"]


def test_old_alerts_are_not_sent_to_new_subscribers(session):
    settings = make_settings()
    alert, _, _ = make_published_alert(session)
    alert.published_at = datetime.now(UTC) - timedelta(hours=5)
    session.commit()
    make_subscriber(session, settings, "+263771000081")  # verified 1 hour ago, after the alert
    provider = MockNotificationProvider()
    assert run(session, settings, provider).queued == 0


def test_delivery_receipts_update_status(session):
    settings = make_settings()
    make_published_alert(session)
    make_subscriber(session, settings, "+263771000091")
    run(session, settings, MockNotificationProvider())
    reference = deliveries(session)[0].provider_reference
    assert svc.apply_delivery_receipt(session, reference, delivered=True) is True
    assert deliveries(session)[0].status == "delivered"
    assert svc.apply_delivery_receipt(session, "unknown-ref", delivered=True) is False
