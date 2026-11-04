"""WhatsApp worker: process stored inbound messages, deliver alerts, purge old data.

The webhook only stores messages (``whatsapp_inbound``); this job does the work, so webhook
requests stay fast and a crash never loses a message. It is a durable PostgreSQL-backed queue:
rows are claimed with ``FOR UPDATE SKIP LOCKED``, retried a bounded number of times, and a message
that keeps failing gets one apology and is marked failed.

Run by the scheduler (``python -m app.jobs.scheduler``) when ``WHATSAPP_ENABLED`` is true, or once
by hand with ``python scripts/run_whatsapp_once.py``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import get_engine
from app.integrations.whatsapp.client import WhatsAppClient, build_client
from app.integrations.whatsapp.messages import text_message
from app.models import WhatsAppConversation, WhatsAppInbound, WhatsAppOutbound
from app.services import alert_notifications
from app.services.notifications import get_notification_provider
from app.services.whatsapp import conversation
from app.services.whatsapp.context import Deps
from app.services.whatsapp.deps import default_deps
from app.services.whatsapp.inbox import release_stale_claims
from app.services.whatsapp.outbound import Replier
from app.services.subscriptions import decrypt_phone

log = logging.getLogger(__name__)

STALE_CLAIM = timedelta(minutes=10)
APOLOGY = "Sorry, something went wrong on our side. Reply MENU to start again."


@dataclass
class DispatchSummary:
    processed: int = 0
    retried: int = 0
    failed: int = 0
    purged: int = 0
    alerts_sent: int = 0
    alerts_queued: int = 0


def _claim(sessions: sessionmaker[Session], limit: int, now: datetime) -> list[uuid.UUID]:
    with sessions.begin() as db:
        release_stale_claims(db, now - STALE_CLAIM)
        rows = db.scalars(
            select(WhatsAppInbound)
            .where(WhatsAppInbound.status == "pending")
            .order_by(func.coalesce(WhatsAppInbound.sent_at, WhatsAppInbound.created_at), WhatsAppInbound.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            row.status = "processing"
            row.attempts += 1
        return [row.id for row in rows]


def process_inbound(
    engine: Engine,
    settings: Settings,
    *,
    client: WhatsAppClient | None = None,
    deps: Deps | None = None,
    now: datetime | None = None,
    limit: int | None = None,
) -> DispatchSummary:
    summary = DispatchSummary()
    now = now or datetime.now(UTC)
    client = client or build_client(settings)
    deps = deps or default_deps(settings)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    ids = _claim(sessions, limit or settings.whatsapp_dispatch_batch_size, now)
    for inbound_id in ids:
        with sessions() as db:
            row = db.get(WhatsAppInbound, inbound_id)
            if row is None:
                continue
            try:
                conversation.process(db, settings, client, deps, row, now=now)
                row.status, row.processed_at, row.last_error = "done", now, None
                row.payload = {}  # the message content is not kept once it has been handled
                db.commit()
                summary.processed += 1
            except Exception as error:  # noqa: BLE001 - one bad message must not stop the batch
                db.rollback()
                log.exception("WhatsApp message processing failed (attempt %d)", row.attempts)
                _record_failure(db, settings, client, inbound_id, error, summary, now)
    return summary


def _record_failure(
    db: Session, settings: Settings, client: WhatsAppClient, inbound_id: uuid.UUID, error: Exception,
    summary: DispatchSummary, now: datetime,
) -> None:
    row = db.get(WhatsAppInbound, inbound_id)
    if row is None:
        return
    row.last_error = type(error).__name__  # never the message or number
    if row.attempts >= settings.whatsapp_max_attempts:
        row.status, row.processed_at, row.payload = "failed", now, {}
        summary.failed += 1
        db.commit()
        try:
            wa_id = decrypt_phone(settings, row.sender_ciphertext).lstrip("+")
            Replier(db, settings, client).send(wa_id, text_message(APOLOGY), key=f"apology:{row.wamid}", kind="apology")
        except Exception:  # noqa: BLE001
            db.rollback()
            log.warning("Could not send the apology for a failed WhatsApp message")
    else:
        row.status = "pending"
        summary.retried += 1
        db.commit()


def deliver_alerts(engine: Engine, settings: Settings, summary: DispatchSummary, *, provider_for=None) -> None:
    """Queue and send WhatsApp alert deliveries through the existing outbox (published, consenting subscribers only)."""
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        provider_for = provider_for or (lambda channel: get_notification_provider(settings, channel))
        result = alert_notifications.run_once(db, settings, provider_for=provider_for, channel="whatsapp")
        summary.alerts_queued, summary.alerts_sent = result.queued, result.sent


def purge(engine: Engine, settings: Settings, now: datetime | None = None) -> int:
    """Delete handled messages, idle conversations and old send logs past the retention period."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=settings.whatsapp_retention_days)
    sessions = sessionmaker(bind=engine)
    with sessions.begin() as db:
        total = 0
        total += db.execute(
            delete(WhatsAppInbound).where(WhatsAppInbound.status.in_(("done", "failed")), WhatsAppInbound.created_at < cutoff)
        ).rowcount or 0
        total += db.execute(delete(WhatsAppConversation).where(WhatsAppConversation.expires_at < cutoff)).rowcount or 0
        total += db.execute(delete(WhatsAppOutbound).where(WhatsAppOutbound.created_at < cutoff)).rowcount or 0
        return total


def run_cycle(engine: Engine, settings: Settings, **kwargs) -> DispatchSummary:
    summary = process_inbound(engine, settings, **{k: v for k, v in kwargs.items() if k in ("client", "deps", "now", "limit")})
    deliver_alerts(engine, settings, summary, provider_for=kwargs.get("provider_for"))
    summary.purged = purge(engine, settings, kwargs.get("now"))
    if summary.processed or summary.retried or summary.failed or summary.alerts_sent or summary.purged:
        log.info(
            "WhatsApp cycle: processed=%d retried=%d failed=%d alerts_queued=%d alerts_sent=%d purged=%d",
            summary.processed, summary.retried, summary.failed, summary.alerts_queued, summary.alerts_sent, summary.purged,
        )
    return summary


def dispatch_whatsapp() -> None:
    """The scheduled job."""
    settings = get_settings()
    if not settings.whatsapp_enabled:
        log.info("WhatsApp bot is disabled (WHATSAPP_ENABLED=false)")
        return
    try:
        run_cycle(get_engine(), settings)
    except Exception:
        log.exception("WhatsApp cycle failed")
        raise
