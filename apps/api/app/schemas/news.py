"""News monitor responses. Only redacted article text is ever exposed."""

from __future__ import annotations

import uuid
from typing import Any

from app.models.enums import (
    EvidenceRole,
    ExtractionStatus,
    FetchStatus,
    IncidentStatus,
    IncidentType,
    ProcessingStatus,
    SourceKind,
)
from app.schemas.common import ApiModel, UtcDatetime


class KeywordRelevance(ApiModel):
    """``relevant`` is None until the keyword screen has run."""

    relevant: bool | None
    reason: str | None


class NewsClassification(ApiModel):
    """How the item has been classified. All fields are additive and optional."""

    status: str  # unscreened | filtered | awaiting_classification | classified | not_relevant | failed
    primary_category: str | None
    primary_subtype: str | None
    candidate_categories: list[str]  # keyword-screen signals, before any AI classification
    record_kind: str | None
    geographic_scope: str | None
    geographic_relevance: str | None  # keyword-screen reading: zimbabwe | regional | unknown | foreign
    editorial_status: str | None
    intelligence_record_id: uuid.UUID | None
    linked_incident_id: uuid.UUID | None


class NewsItemSummary(ApiModel):
    id: uuid.UUID
    source_id: uuid.UUID
    publisher: str
    source_kind: SourceKind
    headline: str
    source_url: str | None
    published_at: UtcDatetime | None
    ingested_at: UtcDatetime
    keyword_relevance: KeywordRelevance
    fetch_status: FetchStatus | None
    processing_status: ProcessingStatus
    extraction_status: ExtractionStatus | None
    linked_incident_count: int
    source_platform: str
    classification: NewsClassification


class ExtractionRunOut(ApiModel):
    id: uuid.UUID
    status: ExtractionStatus
    model_name: str
    prompt_version: str | None
    extraction_confidence: float | None
    input_tokens: int | None
    output_tokens: int | None
    error_message: str | None
    created_at: UtcDatetime
    completed_at: UtcDatetime | None
    output: dict[str, Any] | None


class LinkedIncident(ApiModel):
    id: uuid.UUID
    reference_code: str
    incident_type: IncidentType
    status: IncidentStatus
    evidence_role: EvidenceRole


class NewsItemDetail(NewsItemSummary):
    excerpt: str | None
    article_text: str | None
    fetch_error: str | None
    fetched_at: UtcDatetime | None
    extraction: ExtractionRunOut | None
    incidents: list[LinkedIncident]
