"""WhatsApp bot state: conversations, the durable inbound queue and the outbound message log.

Phone numbers are never stored in the clear. A sender is identified by a keyed digest; the
number needed to reply is kept Fernet-encrypted (same scheme as ``alert_subscribers``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin

INBOUND_STATUSES = ("pending", "processing", "done", "failed")
OUTBOUND_STATUSES = ("queued", "sent", "delivered", "read", "failed")


class WhatsAppConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Where one sender is in the menu. Expires; an expired row is reset to the menu and its draft erased."""

    __tablename__ = "whatsapp_conversations"

    sender_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    flow: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'menu'"))
    step: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'start'"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("sender_digest", name="uq_whatsapp_conversations_sender_digest"),)


class WhatsAppInbound(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One received message, stored by the webhook and processed later by the worker.

    ``wamid`` is Meta's message id: its UNIQUE constraint makes duplicate deliveries harmless.
    """

    __tablename__ = "whatsapp_inbound"

    wamid: Mapped[str] = mapped_column(Text, nullable=False)
    sender_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="Timestamp WhatsApp gave the message.")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("wamid", name="uq_whatsapp_inbound_wamid"),
        CheckConstraint(
            "status IN ('" + "', '".join(INBOUND_STATUSES) + "')", name="status_valid"
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_whatsapp_inbound_status_created_at", "status", "created_at"),
    )


class WhatsAppOutbound(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One message we sent (or tried to). ``idempotency_key`` stops the same reply being sent twice."""

    __tablename__ = "whatsapp_outbound"

    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    sender_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(Text, comment="Meta's id; correlates delivery receipts.")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'queued'"))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_whatsapp_outbound_idempotency_key"),
        CheckConstraint(
            "status IN ('" + "', '".join(OUTBOUND_STATUSES) + "')", name="status_valid"
        ),
        Index("ix_whatsapp_outbound_provider_message_id", "provider_message_id"),
    )
