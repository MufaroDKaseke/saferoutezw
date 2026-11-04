"""Receive side: turn a verified webhook into durable rows. No business logic runs here.

The webhook stores each message in ``whatsapp_inbound`` (unique on Meta's message id, so a
re-delivery is ignored) and applies delivery-status callbacks; the worker does the rest.
Sender numbers are stored as a keyed digest plus Fernet ciphertext only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.rate_limit import check_rate_limit
from app.core.config import Settings
from app.integrations.whatsapp.messages import InboundEvent, ParsedWebhook, StatusEvent
from app.models import WhatsAppInbound, WhatsAppOutbound
from app.services.alert_notifications import apply_delivery_receipt
from app.services.subscriptions import encrypt_phone, keyed_digest

log = logging.getLogger(__name__)

# A status may only move forward; "failed" can follow anything that is not yet delivered.
_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}


def sender_digest(settings: Settings, wa_id: str) -> str:
    return keyed_digest(settings, f"wa:{wa_id}")


def sender_ciphertext(settings: Settings, wa_id: str) -> str:
    return encrypt_phone(settings, "+" + wa_id)


@dataclass
class StoreResult:
    stored: int = 0
    duplicates: int = 0
    rate_limited: int = 0
    statuses: int = 0


def _within_rate_limit(settings: Settings, digest: str) -> bool:
    try:
        check_rate_limit("whatsapp-inbound", digest, settings.whatsapp_user_msgs_per_minute)
    except ApiError:
        return False
    return True


def store_message(session: Session, settings: Settings, event: InboundEvent, result: StoreResult) -> None:
    digest = sender_digest(settings, event.wa_id)
    if not _within_rate_limit(settings, digest):
        result.rate_limited += 1
        log.warning("WhatsApp message dropped: sender over %d/min", settings.whatsapp_user_msgs_per_minute)
        return
    statement = (
        insert(WhatsAppInbound)
        .values(
            wamid=event.wamid,
            sender_digest=digest,
            sender_ciphertext=sender_ciphertext(settings, event.wa_id),
            kind=event.kind,
            payload=event.payload(),
            sent_at=event.sent_at,
        )
        .on_conflict_do_nothing(index_elements=["wamid"])
        .returning(WhatsAppInbound.id)
    )
    if session.execute(statement).first() is None:
        result.duplicates += 1
    else:
        result.stored += 1


def apply_status(session: Session, event: StatusEvent) -> bool:
    """Record a delivery receipt for something we sent. Returns True if it matched a message."""
    matched = False
    row = session.scalar(
        select(WhatsAppOutbound).where(WhatsAppOutbound.provider_message_id == event.provider_message_id)
    )
    if row is not None:
        matched = True
        current = _RANK.get(row.status)
        incoming = _RANK.get(event.status)
        if event.status == "failed" and row.status not in ("delivered", "read"):
            row.status, row.last_error = "failed", f"WhatsApp reported a failure (code {event.error_code or '?'})"
        elif incoming is not None and current is not None and incoming > current:
            row.status = event.status
        row.updated_at = datetime.now(UTC)
    # Alert deliveries are tracked on subscriber_deliveries, keyed by the same provider message id.
    if event.status in ("delivered", "read"):
        matched = apply_delivery_receipt(session, event.provider_message_id, True) or matched
    elif event.status == "failed":
        matched = apply_delivery_receipt(session, event.provider_message_id, False) or matched
    return matched


def store_webhook(session: Session, settings: Settings, parsed: ParsedWebhook) -> StoreResult:
    result = StoreResult()
    for event in parsed.messages:
        store_message(session, settings, event, result)
    for status in parsed.statuses:
        if apply_status(session, status):
            result.statuses += 1
    session.commit()
    return result


def release_stale_claims(session: Session, older_than: datetime) -> int:
    """Messages stuck in ``processing`` (a worker died) go back to ``pending``."""
    updated = session.execute(
        update(WhatsAppInbound)
        .where(WhatsAppInbound.status == "processing", WhatsAppInbound.created_at < older_than)
        .values(status="pending")
    )
    return updated.rowcount or 0
