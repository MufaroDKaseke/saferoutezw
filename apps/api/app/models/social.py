"""Social-media collection: the administrator's allowlist and the quarantine for doubtful posts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CollectionStatus, SocialPlatform, check_in
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SocialSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Social-specific settings and collection state of one ``sources`` row (kind = 'social').

    A social account is collected only if it has a row here *and* ``sources.enabled`` is true.
    ``sources`` keeps the shared fields (name, enabled, polling interval).
    """

    __tablename__ = "social_sources"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    account_url: Mapped[str] = mapped_column(Text, nullable=False, comment="Canonical Page / account URL.")
    platform_account_id: Mapped[str | None] = mapped_column(
        Text, comment="Platform's own id for the account; once known, posts must carry it."
    )
    actor_id: Mapped[str] = mapped_column(Text, nullable=False, comment="Apify Actor, e.g. owner/name.")
    max_posts_per_run: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_post_id: Mapped[str | None] = mapped_column(Text, comment="Newest post accepted so far (cursor).")
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collection_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{CollectionStatus.IDLE.value}'")
    )
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("source_id", name="uq_social_sources_source_id"),
        UniqueConstraint("platform", "account_url", name="uq_social_sources_platform_account_url"),
        CheckConstraint(check_in("platform", SocialPlatform), name="platform_valid"),
        CheckConstraint(check_in("collection_status", CollectionStatus), name="collection_status_valid"),
        CheckConstraint("max_posts_per_run BETWEEN 1 AND 100", name="max_posts_per_run_range"),
    )


class SocialQuarantine(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A scraped post whose origin could not be confirmed. Never enters the pipeline.

    Only a small, non-sensitive summary is kept (no post text, no engagement data).
    """

    __tablename__ = "social_quarantine"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    post_url: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (Index("ix_social_quarantine_source_id_created_at", "source_id", "created_at"),)
