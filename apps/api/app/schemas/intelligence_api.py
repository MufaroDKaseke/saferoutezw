"""Request/response models for the intelligence API (internal editors and the public site).

Public models deliberately omit classification confidence, quality flags, notes, reviewers
and every other internal field.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.common import ApiModel, UtcDatetime
from app.schemas.public import PublicSource
from app.taxonomy import GeographicScope, PrimaryCategory, PublicationOutput, RecordKind, RecordStatus, TemporalStatus

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Headline = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- internal responses


class Citation(ApiModel):
    source_name: str
    source_kind: str
    title: str
    url: str | None
    published_at: UtcDatetime | None


class ObservationOut(ApiModel):
    id: uuid.UUID
    record_id: uuid.UUID
    metric: str
    value: float
    unit: str
    period_start: date | None
    period_end: date | None
    geographic_coverage: str | None
    source_reference: str | None
    methodology: str | None
    comparison_period: str | None
    is_preliminary: bool | None
    verification_status: str


class VersionOut(ApiModel):
    id: uuid.UUID
    version_number: int
    headline: str
    summary: str
    primary_category: PrimaryCategory
    primary_subtype: str | None
    geographic_scope: GeographicScope
    event_date: date | None
    figures: list[dict[str, Any]]
    source_attribution: str | None
    change_note: str | None
    created_by_name: str
    created_at: UtcDatetime
    is_latest: bool


class IntelligenceReviewOut(ApiModel):
    id: uuid.UUID
    version_number: int | None
    decision: str
    notes: str | None
    reviewer_name: str
    reviewed_at: UtcDatetime


class OutputOut(ApiModel):
    id: uuid.UUID
    output_type: PublicationOutput
    status: str
    version_number: int
    published_at: UtcDatetime
    withdrawn_at: UtcDatetime | None


class IntelligenceSummary(ApiModel):
    id: uuid.UUID
    source_item_id: uuid.UUID
    headline: str
    summary: str
    primary_category: PrimaryCategory
    primary_subtype: str | None
    secondary_categories: list[str]
    record_kind: RecordKind
    temporal_status: TemporalStatus
    geographic_scope: GeographicScope
    classification_confidence: float
    status: RecordStatus
    event_date: date | None
    province: str | None
    district_or_town: str | None
    road_name: str | None
    publisher: str
    source_url: str | None
    source_published_at: UtcDatetime | None
    incident_id: uuid.UUID | None
    needs_editorial_review: bool
    topic_key: str | None
    published_outputs: list[PublicationOutput]
    created_at: UtcDatetime


class IntelligenceDetail(IntelligenceSummary):
    location_description: str | None
    country: str | None
    source_attribution: str | None
    taxonomy_version: str
    extraction_version: str
    details: dict[str, Any]
    quality: dict[str, Any]
    citations: list[Citation]
    observations: list[ObservationOut]
    versions: list[VersionOut]
    reviews: list[IntelligenceReviewOut]
    outputs: list[OutputOut]
    allowed_outputs: list[PublicationOutput]


class CategoryCount(ApiModel):
    category: str
    label: str
    subtypes: list[str]
    total: int
    awaiting_review: int
    published: int


class CategoriesOut(ApiModel):
    taxonomy_version: str
    categories: list[CategoryCount]
    record_kinds: list[str]
    temporal_statuses: list[str]
    geographic_scopes: list[str]


class StatisticsSeries(ApiModel):
    metric: str
    unit: str
    geographic_coverage: str | None
    points: list[ObservationOut]


class StatisticsOut(ApiModel):
    series: list[StatisticsSeries]
    note: str


class TrendPoint(ApiModel):
    month: str
    category: str
    count: int


class TrendsOut(ApiModel):
    basis: str
    months: int
    total: int
    points: list[TrendPoint]
    sufficient_data: bool
    caveat: str


class TopicGroup(ApiModel):
    topic_key: str
    category: str
    record_count: int
    publisher_count: int
    first_seen: UtcDatetime
    last_seen: UtcDatetime
    headlines: list[str]


class CorridorCount(ApiModel):
    road_name: str
    category: str
    count: int


class InsightsOut(ApiModel):
    topic_groups: list[TopicGroup]
    corridors: list[CorridorCount]
    new_statistics: list[ObservationOut]
    caveat: str


class OverviewOut(ApiModel):
    by_category: list[CategoryCount]
    awaiting_review: int
    published_by_output: dict[str, int]
    recent: list[IntelligenceSummary]
    latest_statistics: list[ObservationOut]


# --------------------------------------------------------------------------- editorial requests


class FigureDecision(StrictRequest):
    observation_id: uuid.UUID
    status: str = Field(pattern="^(verified|rejected|unverified)$")


class VersionCreate(StrictRequest):
    headline: Headline
    summary: Text
    primary_category: PrimaryCategory
    primary_subtype: str | None = None
    geographic_scope: GeographicScope
    event_date: date | None = None
    source_attribution: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None
    change_note: Notes | None = None
    base_version: int | None = Field(
        default=None, description="The version number this edit starts from; null for the first version."
    )
    figure_decisions: list[FigureDecision] = Field(default_factory=list, max_length=100)


class IntelligenceReviewCreate(StrictRequest):
    decision: str = Field(pattern="^(approved|rejected|needs_changes)$")
    version_id: uuid.UUID | None = None
    notes: Notes | None = None


class PublishOutputRequest(StrictRequest):
    output_type: PublicationOutput


# --------------------------------------------------------------------------- public responses


class PublicTransportItem(ApiModel):
    id: uuid.UUID
    output_type: PublicationOutput
    headline: str
    summary: str
    category: PrimaryCategory
    subtype: str | None
    geographic_scope: GeographicScope
    event_date: date | None
    source_attribution: str | None
    sources: list[PublicSource]
    published_at: UtcDatetime


class PublicStatistic(ApiModel):
    metric: str
    value: float
    unit: str
    period_start: date | None
    period_end: date | None
    geographic_coverage: str | None
    source_reference: str | None
    methodology: str | None
    is_preliminary: bool | None
    published_item_id: uuid.UUID


class PublicStatistics(ApiModel):
    statistics: list[PublicStatistic]
    note: str
