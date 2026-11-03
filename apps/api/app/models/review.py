"""Editorial workflow: versioned bulletin drafts and human review decisions.

``bulletin_versions`` and ``editorial_reviews`` are append-only (enforced by
database triggers): an approval always refers to exactly the text that was
reviewed, and historical decisions are never rewritten.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ReviewDecision, check_in
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.user import User


class BulletinVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An immutable editorial draft. Edits are recorded as a new version."""

    __tablename__ = "bulletin_versions"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    incident: Mapped[Incident] = relationship(back_populates="bulletin_versions")
    author: Mapped[User] = relationship(foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint(
            "incident_id", "version_number", name="uq_bulletin_versions_incident_id_version_number"
        ),
        # Target for composite foreign keys that must stay on the same incident.
        UniqueConstraint("id", "incident_id", name="uq_bulletin_versions_id_incident_id"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(
            "length(btrim(headline)) > 0 AND length(btrim(body)) > 0", name="content_not_blank"
        ),
        Index("ix_bulletin_versions_created_by", "created_by"),
    )


class EditorialReview(UUIDPrimaryKeyMixin, Base):
    """A human decision about a bulletin version (append-only)."""

    __tablename__ = "editorial_reviews"

    incident_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False
    )
    bulletin_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    incident: Mapped[Incident] = relationship(back_populates="reviews")
    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])
    # The composite FK shares ``incident_id`` with the plain FK, so this side is read-only.
    bulletin_version: Mapped[BulletinVersion | None] = relationship(viewonly=True)

    __table_args__ = (
        # The reviewed bulletin version must belong to the same incident.
        ForeignKeyConstraint(
            ["bulletin_version_id", "incident_id"],
            ["bulletin_versions.id", "bulletin_versions.incident_id"],
            ondelete="RESTRICT",
            name="fk_editorial_reviews_bulletin_version_id_bulletin_versions",
        ),
        # Target for public_alerts: pins an alert to one (review, incident, version) triple.
        UniqueConstraint(
            "id",
            "incident_id",
            "bulletin_version_id",
            name="uq_editorial_reviews_id_incident_id_bulletin_version_id",
        ),
        CheckConstraint(check_in("decision", ReviewDecision), name="decision_valid"),
        CheckConstraint(
            "decision <> 'approved' OR bulletin_version_id IS NOT NULL",
            name="approval_requires_bulletin_version",
        ),
        Index("ix_editorial_reviews_incident_id_reviewed_at", "incident_id", "reviewed_at"),
        Index("ix_editorial_reviews_bulletin_version_id", "bulletin_version_id"),
        Index("ix_editorial_reviews_reviewer_id", "reviewer_id"),
    )
