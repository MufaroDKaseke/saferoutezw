"""NUST FM radio bulletins: a timed running order of approved scripts, in numbered revisions.

Prefixed ``radio_`` so nothing collides with the road-safety ``bulletin_versions``. A bulletin has numbered
revisions; each revision lists stories, every one pinned to one exact script version. Changing an approved
bulletin writes a new revision: the approved one stays live until the new one is approved, then the swap is a
single transaction. The database enforces it: ``approved_revision_id`` can only point at an approved revision
that has an approving decision, a revision cannot be approved without one, at most one revision per bulletin
is approved, and the items of a revision that has left draft cannot change. Decisions are append-only and
only an active human editor can record one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import BulletinDecision, RevisionState, check_in
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RadioBulletin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One bulletin: a name, an air time and a target length. Created ad hoc."""

    __tablename__ = "radio_bulletins"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    # The single current approved revision. One column cannot hold two, so there is never a second one.
    approved_revision_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint("target_seconds > 0 AND target_seconds <= 7200", name="target_seconds_in_range"),
        # The approved revision must belong to this bulletin (NULL is not checked).
        ForeignKeyConstraint(
            ["approved_revision_id", "id"],
            ["radio_bulletin_revisions.id", "radio_bulletin_revisions.bulletin_id"],
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_radio_bulletins_approved_revision_id_revisions",
        ),
        Index("ix_radio_bulletins_scheduled_for", "scheduled_for"),
        Index("ix_radio_bulletins_created_by", "created_by"),
    )


class RadioBulletinRevision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A numbered revision: draft -> pending_approval -> approved | rejected; approved -> superseded."""

    __tablename__ = "radio_bulletin_revisions"

    bulletin_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("radio_bulletins.id", ondelete="RESTRICT"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'draft'"))
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aired_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    aired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment="When it was marked as broadcast.")

    __table_args__ = (
        UniqueConstraint("bulletin_id", "revision_number", name="uq_radio_bulletin_revisions_bulletin_id_revision_number"),
        # Target for the composite foreign key that keeps a bulletin's approved pointer on its own revisions.
        UniqueConstraint("id", "bulletin_id", name="uq_radio_bulletin_revisions_id_bulletin_id"),
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
        CheckConstraint(check_in("state", RevisionState), name="state_valid"),
        CheckConstraint("(submitted_by IS NULL) = (submitted_at IS NULL)", name="submitted_by_and_at_together"),
        CheckConstraint("(approved_by IS NULL) = (approved_at IS NULL)", name="approved_by_and_at_together"),
        CheckConstraint("(aired_by IS NULL) = (aired_at IS NULL)", name="aired_by_and_at_together"),
        CheckConstraint("state = 'draft' OR submitted_at IS NOT NULL", name="only_drafts_are_unsubmitted"),
        CheckConstraint(
            "(state IN ('approved', 'superseded')) = (approved_at IS NOT NULL)", name="approval_time_matches_state"
        ),
        CheckConstraint("aired_at IS NULL OR approved_at IS NOT NULL", name="only_approved_revisions_air"),
        # At most one approved revision per bulletin, and at most one still being worked on.
        Index(
            "uq_radio_bulletin_revisions_one_approved",
            "bulletin_id",
            unique=True,
            postgresql_where=text("state = 'approved'"),
        ),
        Index(
            "uq_radio_bulletin_revisions_one_open",
            "bulletin_id",
            unique=True,
            postgresql_where=text("state IN ('draft', 'pending_approval')"),
        ),
        Index("ix_radio_bulletin_revisions_state", "state"),
    )


class RadioBulletinItem(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One story in a revision's running order, pinned to the exact script version that will be read."""

    __tablename__ = "radio_bulletin_items"

    revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("radio_bulletin_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    story_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False)
    script_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    duration_override_seconds: Mapped[int | None] = mapped_column(Integer, comment="For a clip: replaces the reading-time estimate.")
    note: Mapped[str | None] = mapped_column(Text, comment="For the newsreader, for example the clip to play.")

    __table_args__ = (
        # The pinned script must belong to the same story.
        ForeignKeyConstraint(
            ["script_id", "story_id"],
            ["story_scripts.id", "story_scripts.story_id"],
            ondelete="RESTRICT",
            name="fk_radio_bulletin_items_script_id_story_scripts",
        ),
        UniqueConstraint("revision_id", "position", name="uq_radio_bulletin_items_revision_id_position"),
        UniqueConstraint("revision_id", "story_id", name="uq_radio_bulletin_items_revision_id_story_id"),
        CheckConstraint("position >= 1", name="position_positive"),
        CheckConstraint(
            "duration_override_seconds IS NULL OR (duration_override_seconds > 0 AND duration_override_seconds <= 3600)",
            name="duration_override_in_range",
        ),
        Index("ix_radio_bulletin_items_story_id", "story_id"),
        Index("ix_radio_bulletin_items_script_id", "script_id"),
    )


class RadioBulletinDecision(UUIDPrimaryKeyMixin, Base):
    """A human decision about one revision (append-only)."""

    __tablename__ = "radio_bulletin_decisions"

    revision_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        # Named explicitly: the generated name would be 64 characters, one over PostgreSQL's limit.
        ForeignKey("radio_bulletin_revisions.id", ondelete="RESTRICT", name="fk_radio_bulletin_decisions_revision_id_revisions"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    self_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(check_in("decision", BulletinDecision), name="decision_valid"),
        CheckConstraint(
            "decision <> 'rejected' OR (comment IS NOT NULL AND length(btrim(comment)) > 0)",
            name="rejecting_needs_a_comment",
        ),
        CheckConstraint("NOT self_approved OR decision = 'approved'", name="self_approved_only_on_approval"),
        Index("ix_radio_bulletin_decisions_revision_id_decided_at", "revision_id", "decided_at"),
        Index("ix_radio_bulletin_decisions_reviewer_id", "reviewer_id"),
    )
