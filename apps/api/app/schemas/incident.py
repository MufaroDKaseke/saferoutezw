"""Incident list/detail/evidence responses.

Four separate assessments are kept apart on purpose: ``credibility_score`` (is the report
believable), ``geographic_risk_score`` (history of the place), ``extraction_confidence``
(how well the AI read the article) and ``review_priority`` (an ordering aid for editors).
None of them is a calibrated probability.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from app.models.enums import (
    EvidenceRole,
    IncidentStatus,
    IncidentType,
    ReviewPriority,
    Severity,
    VerificationTier,
)
from app.schemas.common import ApiModel, UtcDatetime
from app.schemas.location import LocationOut

ReviewState = Literal["pending_review", "needs_changes", "approved", "rejected", "archived"]


class ExtractedFacts(ApiModel):
    """What the AI reported for the primary article (not verified)."""

    summary: str | None = None
    cause: str | None = None
    fatalities: int | None = None
    injuries: int | None = None
    vehicles_involved: int | None = None
    evidence_quotes: list[str] = []
    extraction_confidence: float | None = None
    model_name: str | None = None
    prompt_version: str | None = None


class Assessments(ApiModel):
    credibility_score: float | None
    geographic_risk_score: float | None
    extraction_confidence: float | None
    review_priority: ReviewPriority
    blackspot_data: Literal["available", "unavailable"] = "unavailable"
    note: str = (
        "Scores are decision aids, not calibrated probabilities. "
        "Credibility is not raised by proximity to a blackspot."
    )


class IncidentSummary(ApiModel):
    id: uuid.UUID
    reference_code: str
    incident_type: IncidentType
    severity: Severity
    status: IncidentStatus
    review_state: ReviewState
    review_priority: ReviewPriority
    summary: str | None
    location_text: str | None
    location_status: str
    has_coordinates: bool
    occurred_at: UtcDatetime | None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    source_count: int
    credibility_score: float | None
    geographic_risk_score: float | None
    latest_bulletin_version: int | None
    extraction_confidence: float | None
    missing_information_count: int


class IncidentDetail(IncidentSummary):
    assessments: Assessments
    extracted_facts: ExtractedFacts | None
    missing_information: list[str]
    location: LocationOut


class EvidenceSource(ApiModel):
    id: uuid.UUID
    publisher: str
    verification_tier: VerificationTier
    headline: str
    source_url: str | None
    published_at: UtcDatetime | None
    received_at: UtcDatetime


class EvidenceOut(ApiModel):
    id: uuid.UUID
    role: EvidenceRole
    created_at: UtcDatetime
    source_item: EvidenceSource
    extraction_status: str | None
    extraction_confidence: float | None
    extraction_output: dict[str, Any] | None
