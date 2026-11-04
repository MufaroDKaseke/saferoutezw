"""Incident candidates and their evidence."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession, Reader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models.enums import IncidentStatus, IncidentType, LocationStatus, ReviewPriority, Severity
from app.repositories import blackspots as blackspot_repo
from app.repositories import incidents as repo
from app.schemas.blackspot import BlackspotMatchesOut
from app.schemas.incident import EvidenceOut, IncidentDetail, IncidentSummary
from app.schemas.location import LocationOut, build_location

router = APIRouter(prefix="/incidents", tags=["incidents"], responses=ERROR_RESPONSES)


def incident_row_or_404(db, incident_id: uuid.UUID):
    row = repo.get_incident_row(db, incident_id)
    if row is None:
        raise not_found("INCIDENT_NOT_FOUND", "The requested incident was not found.")
    return row


@router.get("", response_model=Page[IncidentSummary])
def list_incidents(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    status: IncidentStatus | None = None,
    incident_type: IncidentType | None = None,
    severity: Severity | None = None,
    review_priority: ReviewPriority | None = None,
    location_status: LocationStatus | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Reference code or location contains")] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    sort: Literal["created_at", "occurred_at", "credibility_score", "geographic_risk_score"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> Page[IncidentSummary]:
    filters = repo.IncidentFilters(
        status=status.value if status else None,
        incident_type=incident_type.value if incident_type else None,
        severity=severity.value if severity else None,
        review_priority=review_priority.value if review_priority else None,
        location_status=location_status.value if location_status else None,
        q=q,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
        descending=order == "desc",
    )
    rows, total = paginate(db, repo.incident_list_query(filters), pagination)
    return Page(
        items=repo.build_summaries(db, rows),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: uuid.UUID, auth: Reader, db: DbSession) -> IncidentDetail:
    return repo.build_detail(db, incident_row_or_404(db, incident_id))


@router.get("/{incident_id}/location", response_model=LocationOut)
def get_incident_location(incident_id: uuid.UUID, auth: Reader, db: DbSession) -> LocationOut:
    row = incident_row_or_404(db, incident_id)
    return build_location(row[0], row[1], row[2])


@router.get("/{incident_id}/blackspot-matches", response_model=BlackspotMatchesOut)
def get_incident_blackspot_matches(
    incident_id: uuid.UUID, auth: Reader, db: DbSession, settings: AppSettings
) -> BlackspotMatchesOut:
    row = incident_row_or_404(db, incident_id)
    return blackspot_repo.build_matches(db, row[0], settings.blackspot_match_radius_m)


@router.get("/{incident_id}/evidence", response_model=Page[EvidenceOut])
def list_incident_evidence(
    incident_id: uuid.UUID, auth: Reader, db: DbSession, pagination: Pagination
) -> Page[EvidenceOut]:
    incident_row_or_404(db, incident_id)
    rows, total = paginate(db, repo.evidence_query(incident_id), pagination)
    return Page(
        items=repo.build_evidence(db, rows),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
