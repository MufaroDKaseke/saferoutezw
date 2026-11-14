"""NUST FM story-to-air workflow: stories, immutable script versions and approval decisions.

Prefixed ``story_`` so nothing collides with the road-safety ``bulletin_versions`` / ``editorial_reviews``.
``story_scripts`` and ``story_reviews`` are append-only (database triggers): an approval always refers to
exactly the script text that was reviewed, and a decision is never rewritten.
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
from app.models.enums import ScriptOrigin, StoryDecision, StoryStage, check_in
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Story(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One story for the radio newsroom, optionally built from a collected article."""

    __tablename__ = "stories"

    source_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_items.id", ondelete="RESTRICT"), comment="The article it came from, if any."
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'assigned'"))
    assignee_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_note: Mapped[str | None] = mapped_column(Text, comment="How the reporter checked the facts.")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    follows_story_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("stories.id", ondelete="RESTRICT"), comment="The earlier story this one follows up."
    )

    __table_args__ = (
        CheckConstraint(check_in("stage", StoryStage), name="stage_valid"),
        CheckConstraint("length(btrim(title)) > 0", name="title_not_blank"),
        CheckConstraint(
            "(verified_at IS NULL) = (verified_by IS NULL) AND (verified_at IS NULL) = (verification_note IS NULL)",
            name="verification_all_or_nothing",
        ),
        CheckConstraint(
            "verification_note IS NULL OR length(btrim(verification_note)) > 0", name="verification_note_not_blank"
        ),
        CheckConstraint("follows_story_id IS NULL OR follows_story_id <> id", name="cannot_follow_itself"),
        # An article can only have one live story at a time (a broadcast or dropped one frees it).
        Index(
            "uq_stories_one_open_story_per_article",
            "source_item_id",
            unique=True,
            postgresql_where=text("source_item_id IS NOT NULL AND stage NOT IN ('broadcast', 'dropped')"),
        ),
        Index("ix_stories_assignee_id_stage", "assignee_id", "stage"),
        Index("ix_stories_stage_updated_at", "stage", "updated_at"),
        Index("ix_stories_source_item_id", "source_item_id"),
        Index("ix_stories_follows_story_id", "follows_story_id"),
    )


class StoryScript(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An immutable script version. Editing a script writes a new version."""

    __tablename__ = "story_scripts"

    story_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'human'"))
    # Set only on AI drafts: which model wrote it, from which prompt, at what token cost.
    model_name: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    __table_args__ = (
        UniqueConstraint("story_id", "version_number", name="uq_story_scripts_story_id_version_number"),
        # Target for the composite foreign key that keeps a review on the same story as its script.
        UniqueConstraint("id", "story_id", name="uq_story_scripts_id_story_id"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint("length(btrim(headline)) > 0 AND length(btrim(body)) > 0", name="content_not_blank"),
        CheckConstraint("estimated_seconds >= 0", name="estimated_seconds_non_negative"),
        CheckConstraint(check_in("origin", ScriptOrigin), name="origin_valid"),
        CheckConstraint(
            "origin = 'ai_draft' OR (model_name IS NULL AND prompt_version IS NULL "
            "AND input_tokens IS NULL AND output_tokens IS NULL)",
            name="ai_metadata_only_on_ai_drafts",
        ),
        CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND (output_tokens IS NULL OR output_tokens >= 0)",
            name="tokens_non_negative",
        ),
        Index("ix_story_scripts_created_by", "created_by"),
        Index("ix_story_scripts_origin_created_at", "origin", "created_at"),
    )


class StoryReview(UUIDPrimaryKeyMixin, Base):
    """A human decision about one script version of a story (append-only)."""

    __tablename__ = "story_reviews"

    story_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("stories.id", ondelete="RESTRICT"), nullable=False)
    script_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    self_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # The reviewed script must belong to the same story.
        ForeignKeyConstraint(
            ["script_id", "story_id"],
            ["story_scripts.id", "story_scripts.story_id"],
            ondelete="RESTRICT",
            name="fk_story_reviews_script_id_story_scripts",
        ),
        CheckConstraint(check_in("decision", StoryDecision), name="decision_valid"),
        CheckConstraint(
            "decision <> 'changes_requested' OR (comment IS NOT NULL AND length(btrim(comment)) > 0)",
            name="sending_back_needs_a_comment",
        ),
        CheckConstraint("NOT self_approved OR decision = 'approved'", name="self_approved_only_on_approval"),
        Index("ix_story_reviews_story_id_reviewed_at", "story_id", "reviewed_at"),
        Index("ix_story_reviews_script_id", "script_id"),
        Index("ix_story_reviews_reviewer_id", "reviewer_id"),
    )
