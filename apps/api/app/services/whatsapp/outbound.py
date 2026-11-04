"""Send side: every reply is logged in ``whatsapp_outbound`` under an idempotency key.

A reply's key is derived from the inbound message it answers (``reply:<wamid>:<n>``), so if the
worker crashes after sending and the message is processed again, the user is not messaged twice.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.whatsapp.client import WhatsAppClient
from app.integrations.whatsapp.messages import OutboundMessage
from app.models import WhatsAppOutbound
from app.services.notifications.base import SendResult
from app.services.whatsapp.inbox import sender_digest

log = logging.getLogger(__name__)


class Replier:
    def __init__(self, session: Session, settings: Settings, client: WhatsAppClient) -> None:
        self._session = session
        self._settings = settings
        self._client = client

    def send(self, wa_id: str, message: OutboundMessage, *, key: str, kind: str = "reply") -> SendResult:
        digest = sender_digest(self._settings, wa_id)
        inserted = self._session.execute(
            insert(WhatsAppOutbound)
            .values(idempotency_key=key, sender_digest=digest, kind=kind)
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
            .returning(WhatsAppOutbound.id)
        ).first()
        row = self._session.scalar(select(WhatsAppOutbound).where(WhatsAppOutbound.idempotency_key == key))
        assert row is not None
        if inserted is None and row.status in ("sent", "delivered", "read"):
            return SendResult(status="sent", provider_reference=row.provider_message_id)  # already sent

        result = self._client.send(wa_id, message)
        row.attempts += 1
        row.provider_message_id = result.provider_reference or row.provider_message_id
        if result.status == "failed":
            row.status, row.last_error = "failed", (result.error or "send failed")[:300]
            log.warning("WhatsApp reply failed (kind=%s)", kind)
        else:  # "unknown" is recorded as sent-but-unconfirmed and never retried, to avoid a double send
            row.status = "sent"
            row.last_error = result.error if result.status == "unknown" else None
        self._session.commit()
        return result
