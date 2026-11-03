"""Public alerts and the outbound delivery pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import AlertStatus, AttemptStatus, ChannelKind, OutboxStatus, check_in
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.review import BulletinVersion, EditorialReview


class PublicAlert(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A public-facing bulletin backed by a human approval.

    Composite foreign keys pin the alert to one incident / bulletin version /
    approving review triple, and a database trigger additionally requires that
    review to be an ``approved`` decision by an active human editor.
    Public APIs must read only from this table (never from drafts).
    """

    __tablename__ = "public_alerts"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    bulletin_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    approval_review_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{AlertStatus.READY.value}'")
    )

    incident: Mapped[Incident] = relationship(back_populates="public_alerts")
    # Composite FKs overlap the plain ``incident_id`` FK, so these are read-only.
    bulletin_version: Mapped[BulletinVersion] = relationship(viewonly=True)
    approval_review: Mapped[EditorialReview] = relationship(viewonly=True)
    outbox_entries: Mapped[list[NotificationOutbox]] = relationship(
        back_populates="public_alert", passive_deletes="all"
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["bulletin_version_id", "incident_id"],
            ["bulletin_versions.id", "bulletin_versions.incident_id"],
            ondelete="RESTRICT",
            name="fk_public_alerts_bulletin_version_id_bulletin_versions",
        ),
        ForeignKeyConstraint(
            ["approval_review_id", "incident_id", "bulletin_version_id"],
            [
                "editorial_reviews.id",
                "editorial_reviews.incident_id",
                "editorial_reviews.bulletin_version_id",
            ],
            ondelete="RESTRICT",
            name="fk_public_alerts_approval_review_id_editorial_reviews",
        ),
        UniqueConstraint("approval_review_id", name="uq_public_alerts_approval_review_id"),
        UniqueConstraint("bulletin_version_id", name="uq_public_alerts_bulletin_version_id"),
        CheckConstraint(check_in("status", AlertStatus), name="status_valid"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_requires_published_at",
        ),
        Index("ix_public_alerts_incident_id", "incident_id"),
        Index("ix_public_alerts_status_published_at", "status", "published_at"),
    )


class DeliveryChannel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A configured outbound channel (web, email, SMS, ...)."""

    __tablename__ = "delivery_channels"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    outbox_entries: Mapped[list[NotificationOutbox]] = relationship(
        back_populates="channel", passive_deletes="all"
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_delivery_channels_name"),
        CheckConstraint(check_in("kind", ChannelKind), name="kind_valid"),
    )


class NotificationOutbox(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A pending delivery of one public alert on one channel (idempotent)."""

    __tablename__ = "notification_outbox"

    public_alert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("public_alerts.id", ondelete="RESTRICT"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("delivery_channels.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{OutboxStatus.PENDING.value}'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    public_alert: Mapped[PublicAlert] = relationship(back_populates="outbox_entries")
    channel: Mapped[DeliveryChannel] = relationship(back_populates="outbox_entries")
    delivery_attempts: Mapped[list[DeliveryAttempt]] = relationship(
        back_populates="outbox", passive_deletes="all"
    )

    __table_args__ = (
        # Idempotency: an alert is queued at most once per channel, so a retry
        # or a double-submit can never produce a duplicate delivery.
        UniqueConstraint(
            "public_alert_id", "channel_id", name="uq_notification_outbox_public_alert_id_channel_id"
        ),
        CheckConstraint(check_in("status", OutboxStatus), name="status_valid"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index("ix_notification_outbox_status_next_attempt_at", "status", "next_attempt_at"),
        Index("ix_notification_outbox_channel_id", "channel_id"),
    )


class DeliveryAttempt(UUIDPrimaryKeyMixin, Base):
    """One attempt to deliver an outbox entry (history is preserved)."""

    __tablename__ = "delivery_attempts"

    outbox_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("notification_outbox.id", ondelete="RESTRICT"), nullable=False
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)

    outbox: Mapped[NotificationOutbox] = relationship(back_populates="delivery_attempts")

    __table_args__ = (
        CheckConstraint(check_in("status", AttemptStatus), name="status_valid"),
        Index("ix_delivery_attempts_outbox_id_attempted_at", "outbox_id", "attempted_at"),
    )
