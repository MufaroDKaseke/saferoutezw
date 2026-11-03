"""Audit trail of significant application activity (append-only)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class AuditEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An immutable record of who did what to which entity.

    A database trigger rejects UPDATE and DELETE. ``details`` must never carry
    personal data, secrets or credentials - record identifiers and state
    changes only.
    """

    __tablename__ = "audit_events"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        comment="NULL for system-originated events.",
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_user_id])

    __table_args__ = (
        CheckConstraint(
            "length(btrim(action)) > 0 AND length(btrim(entity_type)) > 0",
            name="action_and_entity_type_not_blank",
        ),
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_events_actor_user_id_created_at", "actor_user_id", "created_at"),
        Index("ix_audit_events_created_at", "created_at"),
    )
