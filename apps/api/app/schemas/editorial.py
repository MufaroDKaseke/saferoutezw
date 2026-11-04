"""Editorial requests and responses.

Request models forbid unknown fields: a client that sends ``reviewer_id`` (to impersonate
someone) is rejected, because the reviewer is always taken from the authenticated session.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models.enums import ReviewDecision
from app.schemas.common import ApiModel, UtcDatetime
from app.schemas.incident import IncidentSummary

Headline = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BulletinCreate(StrictRequest):
    headline: Headline
    body: Body
    base_version: int | None = Field(
        default=None,
        ge=1,
        description="The latest version number the editor was looking at (null when there is none yet). "
        "A different current version is a conflict, so two editors cannot silently overwrite each other.",
    )


class BulletinOut(ApiModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    version_number: int
    headline: str
    body: str
    created_by: uuid.UUID
    created_by_name: str | None
    created_at: UtcDatetime
    is_latest: bool


class ReviewCreate(StrictRequest):
    decision: ReviewDecision
    bulletin_version_id: uuid.UUID | None = Field(
        default=None, description="Required to approve: the exact version being approved (must be the latest)."
    )
    notes: Notes | None = None

    @model_validator(mode="after")
    def _requirements(self) -> "ReviewCreate":
        if self.decision == ReviewDecision.APPROVED and self.bulletin_version_id is None:
            raise ValueError("bulletin_version_id is required to approve")
        if self.decision != ReviewDecision.APPROVED and not (self.notes or "").strip():
            raise ValueError("notes are required to reject or request changes")
        return self


class ReviewOut(ApiModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    bulletin_version_id: uuid.UUID | None
    version_number: int | None
    decision: ReviewDecision
    notes: str | None
    reviewer_id: uuid.UUID
    reviewer_name: str | None
    reviewed_at: UtcDatetime


class ReviewResult(ApiModel):
    review: ReviewOut
    incident: IncidentSummary


class LocationConfirmRequest(StrictRequest):
    action: Literal["accept_proposed", "select_candidate", "set_coordinates", "mark_unresolved"]
    candidate_index: int | None = Field(default=None, ge=0, le=20)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    precision_meters: float | None = Field(default=None, ge=0, le=100_000)
    note: Notes | None = None

    @model_validator(mode="after")
    def _requirements(self) -> "LocationConfirmRequest":
        if self.action == "select_candidate" and self.candidate_index is None:
            raise ValueError("candidate_index is required to select a candidate")
        if self.action == "set_coordinates" and (self.latitude is None or self.longitude is None):
            raise ValueError("latitude and longitude are required to set coordinates")
        return self


class ReviewCounts(ApiModel):
    """Incidents per derived review state (archived ones count as approved)."""

    pending: int
    needs_changes: int
    approved: int
    rejected: int
