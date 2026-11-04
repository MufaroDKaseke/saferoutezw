"""Transport intelligence: classified interpretations of source items.

An *intelligence record* is a structured reading of one source item (article, post, report).
It is NOT an incident: policy, statistics and infrastructure announcements live only here.
Only an actionable record (``record_kind = actionable_event`` in an actionable category) may
point at an ``incidents`` row, and a CHECK constraint enforces that.

Editorial history mirrors the incident workflow: ``intelligence_versions`` and
``intelligence_reviews`` are append-only (database triggers), and a ``publication_outputs`` row
(a separate, explicit action) pins one approved version to one output type. None of this can
produce a public hazard alert; those still come only from ``public_alerts``.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ReviewDecision, check_in
from app.models.mixins import CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.taxonomy import (
    ACTIONABLE_CATEGORIES,
    ALL_SUBTYPES,
    GeographicScope,
    PrimaryCategory,
    PublicationOutput as PublicationOutputType,
    RecordKind,
    RecordStatus,
    TemporalStatus,
    subtype_category_check_sql,
)

if TYPE_CHECKING:
    from app.models.evidence import ExtractionRun
    from app.models.incident import Incident
    from app.models.source import SourceItem
    from app.models.user import User

_ACTIONABLE_SQL = ", ".join(f"'{c.value}'" for c in sorted(ACTIONABLE_CATEGORIES, key=lambda c: c.value))


def _in(column: str, values: list[str] | tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class IntelligenceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One classified reading of one source item. AI output is a candidate until reviewed."""

    __tablename__ = "intelligence_records"

    source_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("source_items.id", ondelete="RESTRICT"), nullable=False
    )
    extraction_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("extraction_runs.id", ondelete="RESTRICT")
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("incidents.id", ondelete="RESTRICT"),
        comment="Only actionable events link to an incident.",
    )
    extraction_version: Mapped[str] = mapped_column(String(48), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(24), nullable=False)

    primary_category: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_subtype: Mapped[str | None] = mapped_column(String(40))
    secondary_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), nullable=False, server_default=text("'{}'::varchar[]")
    )
    record_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    temporal_status: Mapped[str] = mapped_column(String(16), nullable=False)
    geographic_scope: Mapped[str] = mapped_column(String(24), nullable=False)
    classification_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    neutral_summary: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    location_description: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    province: Mapped[str | None] = mapped_column(Text)
    district_or_town: Mapped[str | None] = mapped_column(Text)
    road_name: Mapped[str | None] = mapped_column(Text)
    source_attribution: Mapped[str | None] = mapped_column(Text)
    topic_key: Mapped[str | None] = mapped_column(
        Text, comment="Groups follow-up items about one project, policy or report; not a dedup key."
    )

    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
        comment="Category-specific payload, validated against app.schemas.intelligence.",
    )
    quality: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"),
        comment="Data-quality flags, missing information, evidence quotes, review hints.",
    )
    needs_editorial_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{RecordStatus.CANDIDATE.value}'")
    )

    source_item: Mapped[SourceItem] = relationship()
    extraction_run: Mapped[ExtractionRun | None] = relationship()
    incident: Mapped[Incident | None] = relationship()
    observations: Mapped[list[StatisticalObservation]] = relationship(
        back_populates="record", order_by="StatisticalObservation.created_at"
    )
    versions: Mapped[list[IntelligenceVersion]] = relationship(
        back_populates="record", order_by="IntelligenceVersion.version_number"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_item_id", "extraction_version",
            name="uq_intelligence_records_source_item_id_extraction_version",
        ),
        CheckConstraint(check_in("primary_category", PrimaryCategory), name="primary_category_valid"),
        CheckConstraint(
            f"primary_subtype IS NULL OR {_in('primary_subtype', ALL_SUBTYPES)}",
            name="primary_subtype_valid",
        ),
        CheckConstraint(subtype_category_check_sql("primary_category", "primary_subtype"),
                        name="subtype_matches_category"),
        CheckConstraint(check_in("record_kind", RecordKind), name="record_kind_valid"),
        CheckConstraint(check_in("temporal_status", TemporalStatus), name="temporal_status_valid"),
        CheckConstraint(check_in("geographic_scope", GeographicScope), name="geographic_scope_valid"),
        CheckConstraint(check_in("status", RecordStatus), name="status_valid"),
        CheckConstraint("classification_confidence BETWEEN 0 AND 1", name="confidence_range"),
        CheckConstraint(
            "length(btrim(headline)) > 0 AND length(btrim(neutral_summary)) > 0",
            name="content_not_blank",
        ),
        # Policy, statistics, projects and campaigns can never be (or point at) an incident.
        CheckConstraint(
            f"incident_id IS NULL OR (record_kind = 'actionable_event' AND primary_category IN ({_ACTIONABLE_SQL}))",
            name="only_actionable_events_link_incidents",
        ),
        Index("ix_intelligence_records_category_status_created", "primary_category", "status", "created_at"),
        Index("ix_intelligence_records_record_kind", "record_kind"),
        Index("ix_intelligence_records_event_date", "event_date"),
        Index("ix_intelligence_records_province", "province"),
        Index("ix_intelligence_records_topic_key", "topic_key"),
        Index("ix_intelligence_records_incident_id", "incident_id"),
        Index("ix_intelligence_records_extraction_run_id", "extraction_run_id"),
    )


class StatisticalObservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One reported figure with its period, coverage and source. Never aggregated across
    different periods or definitions, and never used as an incident count."""

    __tablename__ = "statistical_observations"

    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intelligence_records.id", ondelete="RESTRICT"), nullable=False
    )
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    geographic_coverage: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    methodology: Mapped[str | None] = mapped_column(Text)
    comparison_period: Mapped[str | None] = mapped_column(Text)
    is_preliminary: Mapped[bool | None] = mapped_column(Boolean)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'unverified'")
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    record: Mapped[IntelligenceRecord] = relationship(back_populates="observations")

    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')", name="verification_status_valid"
        ),
        CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_end >= period_start", name="period_order"
        ),
        CheckConstraint(
            "verification_status = 'unverified' OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="verification_has_actor",
        ),
        Index("ix_statistical_observations_record_id", "record_id"),
        Index("ix_statistical_observations_metric_period", "metric", "period_start", "period_end"),
        Index("ix_statistical_observations_verified_by", "verified_by"),
    )


class IntelligenceVersion(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An immutable editorial snapshot: what a reviewer approved is exactly this."""

    __tablename__ = "intelligence_versions"

    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intelligence_records.id", ondelete="RESTRICT"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    primary_category: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_subtype: Mapped[str | None] = mapped_column(String(40))
    geographic_scope: Mapped[str] = mapped_column(String(24), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    figures: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"),
        comment="Snapshot of the confirmed statistical observations.",
    )
    source_attribution: Mapped[str | None] = mapped_column(Text)
    change_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    record: Mapped[IntelligenceRecord] = relationship(back_populates="versions")
    author: Mapped[User] = relationship(foreign_keys=[created_by])

    __table_args__ = (
        UniqueConstraint("record_id", "version_number", name="uq_intelligence_versions_record_id_version_number"),
        UniqueConstraint("id", "record_id", name="uq_intelligence_versions_id_record_id"),
        CheckConstraint("version_number >= 1", name="version_number_positive"),
        CheckConstraint(check_in("primary_category", PrimaryCategory), name="primary_category_valid"),
        CheckConstraint(check_in("geographic_scope", GeographicScope), name="geographic_scope_valid"),
        CheckConstraint(subtype_category_check_sql("primary_category", "primary_subtype"),
                        name="subtype_matches_category"),
        CheckConstraint(
            "length(btrim(headline)) > 0 AND length(btrim(summary)) > 0", name="content_not_blank"
        ),
        Index("ix_intelligence_versions_created_by", "created_by"),
    )


class IntelligenceReview(UUIDPrimaryKeyMixin, Base):
    """A human decision about one intelligence version (append-only)."""

    __tablename__ = "intelligence_reviews"

    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intelligence_records.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])

    __table_args__ = (
        ForeignKeyConstraint(
            ["version_id", "record_id"],
            ["intelligence_versions.id", "intelligence_versions.record_id"],
            ondelete="RESTRICT",
            name="fk_intelligence_reviews_version_id_intelligence_versions",
        ),
        UniqueConstraint(
            "id", "record_id", "version_id", name="uq_intelligence_reviews_id_record_id_version_id"
        ),
        CheckConstraint(check_in("decision", ReviewDecision), name="decision_valid"),
        CheckConstraint(
            "decision <> 'approved' OR version_id IS NOT NULL", name="approval_requires_version"
        ),
        Index("ix_intelligence_reviews_record_id_reviewed_at", "record_id", "reviewed_at"),
        Index("ix_intelligence_reviews_version_id", "version_id"),
        Index("ix_intelligence_reviews_reviewer_id", "reviewer_id"),
    )


class PublicationOutput(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """A separate, explicit publication of one approved version as one output type.

    This is never a hazard alert. ``public_alerts`` remains the only road-hazard channel.
    """

    __tablename__ = "publication_outputs"

    record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("intelligence_records.id", ondelete="RESTRICT"), nullable=False
    )
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    approval_review_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    output_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'published'"))
    published_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    record: Mapped[IntelligenceRecord] = relationship()

    __table_args__ = (
        ForeignKeyConstraint(
            ["approval_review_id", "record_id", "version_id"],
            ["intelligence_reviews.id", "intelligence_reviews.record_id", "intelligence_reviews.version_id"],
            ondelete="RESTRICT",
            name="fk_publication_outputs_approval_review_id_intelligence_reviews",
        ),
        UniqueConstraint("version_id", "output_type", name="uq_publication_outputs_version_id_output_type"),
        CheckConstraint(
            check_in("output_type", PublicationOutputType),
            name="output_type_valid",
        ),
        CheckConstraint("status IN ('published', 'withdrawn')", name="status_valid"),
        CheckConstraint("status <> 'withdrawn' OR withdrawn_at IS NOT NULL", name="withdrawn_has_timestamp"),
        Index("ix_publication_outputs_record_id", "record_id"),
        Index("ix_publication_outputs_type_status_published", "output_type", "status", "published_at"),
        Index("ix_publication_outputs_published_by", "published_by"),
    )
