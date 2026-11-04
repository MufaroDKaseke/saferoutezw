"""Public alert subscribers (phone based, no accounts).

Phone numbers are stored encrypted (``phone_ciphertext``); ``phone_digest`` is a keyed
HMAC used only for de-duplication and lookup. One-time codes are never stored in clear:
only a keyed hash. Management tokens are stored as SHA-256 hashes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import check_in
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class SubscriberStatus(StrEnum):
    PENDING = "pending"  # number typed in, not yet verified: never receives alerts
    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"


class SubscriberChannel(StrEnum):
    SMS = "sms"
    WHATSAPP = "whatsapp"


class ChallengePurpose(StrEnum):
    ACTIVATE = "activate"
    MANAGE = "manage"


class DeliveryState(StrEnum):
    QUEUED = "queued"
    SENT = "sent"  # accepted by the provider; no delivery receipt yet
    DELIVERED = "delivered"  # provider confirmed delivery
    FAILED = "failed"
    UNKNOWN = "unknown"  # provider could not tell us


class AlertSubscriber(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "alert_subscribers"

    phone_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    phone_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{SubscriberStatus.PENDING.value}'")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("phone_digest", name="uq_alert_subscribers_phone_digest"),
        CheckConstraint(check_in("channel", SubscriberChannel), name="channel_valid"),
        CheckConstraint(check_in("status", SubscriberStatus), name="status_valid"),
        CheckConstraint(
            "status <> 'active' OR verified_at IS NOT NULL", name="active_requires_verification"
        ),
        Index("ix_alert_subscribers_status_channel", "status", "channel"),
    )


class SubscriptionPreference(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "subscription_preferences"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("alert_subscribers.id", ondelete="CASCADE"), nullable=False
    )
    all_zimbabwe: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    provinces: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    corridors: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("subscriber_id", name="uq_subscription_preferences_subscriber_id"),)


class SubscriptionChallenge(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "subscription_challenges"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("alert_subscribers.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(check_in("purpose", ChallengePurpose), name="purpose_valid"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_subscription_challenges_subscriber_id_created_at", "subscriber_id", "created_at"),
    )


class SubscriptionConsent(UUIDPrimaryKeyMixin, Base):
    """Evidence of explicit opt-in (and its withdrawal)."""

    __tablename__ = "subscription_consents"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("alert_subscribers.id", ondelete="CASCADE"), nullable=False
    )
    consent_text_version: Mapped[str] = mapped_column(String(32), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ip_digest: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(check_in("channel", SubscriberChannel), name="channel_valid"),
        Index("ix_subscription_consents_subscriber_id", "subscriber_id"),
    )


class SubscriptionToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Short-lived bearer token issued after a successful verification."""

    __tablename__ = "subscription_tokens"

    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("alert_subscribers.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_subscription_tokens_token_hash"),
        Index("ix_subscription_tokens_subscriber_id", "subscriber_id"),
    )


class SubscriberDelivery(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One alert to one subscriber. ``idempotency_key`` makes worker retries safe."""

    __tablename__ = "subscriber_deliveries"

    public_alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("public_alerts.id", ondelete="RESTRICT"), nullable=False
    )
    subscriber_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("alert_subscribers.id", ondelete="RESTRICT"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{DeliveryState.QUEUED.value}'")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(32))
    provider_reference: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_subscriber_deliveries_idempotency_key"),
        CheckConstraint(check_in("channel", SubscriberChannel), name="channel_valid"),
        CheckConstraint(check_in("status", DeliveryState), name="status_valid"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_subscriber_deliveries_status_next_attempt_at", "status", "next_attempt_at"),
        Index("ix_subscriber_deliveries_public_alert_id", "public_alert_id"),
        Index("ix_subscriber_deliveries_subscriber_id", "subscriber_id"),
    )
