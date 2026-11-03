"""Source ingestion: sources, ingestion runs and individual source items."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import (
    FetchStatus,
    IngestionStatus,
    ProcessingStatus,
    SourceKind,
    VerificationTier,
    check_in,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.evidence import ExtractionRun, IncidentEvidence


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An RSS feed, official channel, WhatsApp/social source or manual origin."""

    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    feed_url: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("900")
    )
    verification_tier: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text(f"'{VerificationTier.UNVERIFIED.value}'"),
    )
    rights_notes: Mapped[str | None] = mapped_column(
        Text, comment="Licensing / reuse terms recorded for this source."
    )

    ingestion_runs: Mapped[list[IngestionRun]] = relationship(
        back_populates="source", passive_deletes="all"
    )
    items: Mapped[list[SourceItem]] = relationship(
        back_populates="source", passive_deletes="all"
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_sources_name"),
        UniqueConstraint("feed_url", name="uq_sources_feed_url"),
        CheckConstraint(check_in("kind", SourceKind), name="kind_valid"),
        CheckConstraint(
            check_in("verification_tier", VerificationTier), name="verification_tier_valid"
        ),
        CheckConstraint("poll_interval_seconds >= 60", name="poll_interval_min"),
        CheckConstraint("kind <> 'rss' OR feed_url IS NOT NULL", name="rss_requires_feed_url"),
        Index("ix_sources_enabled_kind", "enabled", "kind"),
    )


class IngestionRun(UUIDPrimaryKeyMixin, Base):
    """One execution of an ingestion job against a source."""

    __tablename__ = "ingestion_runs"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text(f"'{IngestionStatus.RUNNING.value}'"),
    )
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source] = relationship(back_populates="ingestion_runs")
    items: Mapped[list[SourceItem]] = relationship(
        back_populates="ingestion_run", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(check_in("status", IngestionStatus), name="status_valid"),
        CheckConstraint(
            "fetched_count >= 0 AND inserted_count >= 0 "
            "AND duplicate_count >= 0 AND error_count >= 0",
            name="counts_non_negative",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="completed_after_started"
        ),
        Index("ix_ingestion_runs_source_id_started_at", "source_id", "started_at"),
    )


class SourceItem(UUIDPrimaryKeyMixin, Base):
    """A single incoming report or news entry. Stores redacted text only."""

    __tablename__ = "source_items"

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False
    )
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ingestion_runs.id", ondelete="SET NULL")
    )
    external_id: Mapped[str | None] = mapped_column(
        Text, comment="Feed GUID / provider message id, unique per source."
    )
    canonical_url: Mapped[str | None] = mapped_column(
        Text, comment="URL with tracking parameters stripped, unique per source."
    )
    title_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt_redacted: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=text(f"'{ProcessingStatus.PENDING.value}'"),
    )
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # Full-article stage (app.services.pipeline). The text is stored only after redaction.
    article_text_redacted: Mapped[str | None] = mapped_column(
        Text, comment="Full article text after privacy redaction; the only text sent to the AI."
    )
    fetch_status: Mapped[str | None] = mapped_column(String(16))
    fetch_error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(
        String(64), comment="SHA-256 of article_text_redacted; detects syndicated copies."
    )
    screen_reason: Mapped[str | None] = mapped_column(
        Text, comment="Keyword screen outcome, e.g. matched terms or why it was filtered."
    )

    source: Mapped[Source] = relationship(back_populates="items")
    ingestion_run: Mapped[IngestionRun | None] = relationship(back_populates="items")
    extraction_runs: Mapped[list[ExtractionRun]] = relationship(
        back_populates="source_item", passive_deletes="all"
    )
    evidence_links: Mapped[list[IncidentEvidence]] = relationship(
        back_populates="source_item", passive_deletes="all"
    )

    __table_args__ = (
        # Deduplication: the same feed entry can only be stored once per source,
        # whether it is identified by its GUID or by its canonical URL.
        UniqueConstraint("source_id", "external_id", name="uq_source_items_source_id_external_id"),
        UniqueConstraint(
            "source_id", "canonical_url", name="uq_source_items_source_id_canonical_url"
        ),
        CheckConstraint(
            "external_id IS NOT NULL OR canonical_url IS NOT NULL",
            name="has_dedup_key",
        ),
        CheckConstraint(check_in("processing_status", ProcessingStatus), name="processing_status_valid"),
        CheckConstraint(
            f"fetch_status IS NULL OR {check_in('fetch_status', FetchStatus)}",
            name="fetch_status_valid",
        ),
        Index("ix_source_items_content_hash", "content_hash"),
        Index("ix_source_items_processing_status_received_at", "processing_status", "received_at"),
        Index("ix_source_items_published_at", "published_at"),
        Index("ix_source_items_ingestion_run_id", "ingestion_run_id"),
    )
