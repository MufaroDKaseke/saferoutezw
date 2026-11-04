"""Editorial workflow endpoints (writes need an editor or admin; analysts may read)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import case, func, or_, select

from app.api.deps import AppSettings, DbSession, Editor, Reader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models import BulletinVersion, EditorialReview, Incident, User
from app.models.enums import IncidentStatus, ReviewPriority
from app.repositories import incidents as incident_repo
from app.schemas.editorial import (
    BulletinCreate,
    BulletinOut,
    LocationConfirmRequest,
    ReviewCreate,
    ReviewCounts,
    ReviewOut,
    ReviewResult,
)
from app.schemas.incident import IncidentSummary
from app.schemas.location import LocationOut
from app.services import editorial

router = APIRouter(tags=["editorial"], responses=ERROR_RESPONSES)

OPEN = (IncidentStatus.CANDIDATE.value, IncidentStatus.UNDER_REVIEW.value)
PRIORITY_RANK = case(
    {"urgent": 0, "high": 1, "normal": 2, "low": 3}, value=Incident.review_priority, else_=4
)


def _ensure_incident(db, incident_id: uuid.UUID) -> None:
    if db.get(Incident, incident_id) is None:
        raise not_found("INCIDENT_NOT_FOUND", "The requested incident was not found.")


def _bulletin_out(version: BulletinVersion, author: str | None, latest_number: int) -> BulletinOut:
    return BulletinOut(
        id=version.id,
        incident_id=version.incident_id,
        version_number=version.version_number,
        headline=version.headline,
        body=version.body,
        created_by=version.created_by,
        created_by_name=author,
        created_at=version.created_at,
        is_latest=version.version_number == latest_number,
    )


def _review_out(review: EditorialReview, reviewer: str | None, version_number: int | None) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        incident_id=review.incident_id,
        bulletin_version_id=review.bulletin_version_id,
        version_number=version_number,
        decision=review.decision,
        notes=review.notes,
        reviewer_id=review.reviewer_id,
        reviewer_name=reviewer,
        reviewed_at=review.reviewed_at,
    )


@router.get("/reviews/counts", response_model=ReviewCounts)
def get_review_counts(auth: Reader, db: DbSession) -> ReviewCounts:
    """How many incidents are in each review state (derived from status and the latest decision)."""
    counts = {"pending": 0, "needs_changes": 0, "approved": 0, "rejected": 0}
    closed = dict(db.execute(select(Incident.status, func.count()).group_by(Incident.status)).all())
    counts["approved"] = sum(closed.get(s, 0) for s in ("approved", "published", "archived"))
    counts["rejected"] = closed.get("rejected", 0)
    open_ids = list(db.scalars(select(Incident.id).where(Incident.status.in_(OPEN))))
    extras = incident_repo.load_extras(db, open_ids)
    for incident_id in open_ids:
        state = incident_repo.derive_review_state("under_review", extras[incident_id])
        counts["needs_changes" if state == "needs_changes" else "pending"] += 1
    return ReviewCounts(**counts)


@router.get("/reviews/pending", response_model=Page[IncidentSummary])
def list_pending_reviews(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200, description="Reference code or location contains")] = None,
    review_priority: ReviewPriority | None = None,
) -> Page[IncidentSummary]:
    """Incidents waiting for an editorial decision: most urgent first, then oldest first."""
    query = select(Incident, incident_repo.LAT, incident_repo.LNG).where(Incident.status.in_(OPEN))
    if q:
        pattern = incident_repo._like(q.strip())
        query = query.where(or_(Incident.reference_code.ilike(pattern), Incident.location_text.ilike(pattern)))
    if review_priority:
        query = query.where(Incident.review_priority == review_priority.value)
    query = query.order_by(PRIORITY_RANK, Incident.created_at, Incident.id)
    rows, total = paginate(db, query, pagination)
    return Page(
        items=incident_repo.build_summaries(db, rows),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/incidents/{incident_id}/bulletins", response_model=Page[BulletinOut])
def list_bulletin_versions(
    incident_id: uuid.UUID, auth: Reader, db: DbSession, pagination: Pagination
) -> Page[BulletinOut]:
    _ensure_incident(db, incident_id)
    latest = db.scalar(
        select(func.max(BulletinVersion.version_number)).where(BulletinVersion.incident_id == incident_id)
    )
    query = (
        select(BulletinVersion, User.display_name)
        .join(User, User.id == BulletinVersion.created_by)
        .where(BulletinVersion.incident_id == incident_id)
        .order_by(BulletinVersion.version_number.desc())
    )
    rows, total = paginate(db, query, pagination)
    return Page(
        items=[_bulletin_out(v, name, latest or 0) for v, name in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("/incidents/{incident_id}/bulletins", response_model=BulletinOut, status_code=status.HTTP_201_CREATED)
def create_bulletin_version(
    incident_id: uuid.UUID, body: BulletinCreate, auth: Editor, db: DbSession
) -> BulletinOut:
    """Save a new immutable bulletin version (never edits an existing one)."""
    version, _ = editorial.save_bulletin(db, auth.user, incident_id, body.headline, body.body, body.base_version)
    return _bulletin_out(version, auth.user.display_name, version.version_number)


@router.get("/incidents/{incident_id}/reviews", response_model=Page[ReviewOut])
def list_incident_reviews(
    incident_id: uuid.UUID, auth: Reader, db: DbSession, pagination: Pagination
) -> Page[ReviewOut]:
    """The append-only decision history of an incident, newest first."""
    _ensure_incident(db, incident_id)
    query = (
        select(EditorialReview, User.display_name, BulletinVersion.version_number)
        .join(User, User.id == EditorialReview.reviewer_id)
        .outerjoin(BulletinVersion, BulletinVersion.id == EditorialReview.bulletin_version_id)
        .where(EditorialReview.incident_id == incident_id)
        .order_by(EditorialReview.reviewed_at.desc(), EditorialReview.id)
    )
    rows, total = paginate(db, query, pagination)
    return Page(
        items=[_review_out(r, name, number) for r, name, number in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("/incidents/{incident_id}/reviews", response_model=ReviewResult, status_code=status.HTTP_201_CREATED)
def create_review(incident_id: uuid.UUID, body: ReviewCreate, auth: Editor, db: DbSession) -> ReviewResult:
    """Approve, reject or request changes. The reviewer is the signed-in user."""
    review, _ = editorial.record_review(
        db, auth.user, incident_id, body.decision, body.bulletin_version_id, body.notes
    )
    number = db.scalar(
        select(BulletinVersion.version_number).where(BulletinVersion.id == review.bulletin_version_id)
    )
    row = incident_repo.get_incident_row(db, incident_id)
    return ReviewResult(
        review=_review_out(review, auth.user.display_name, number),
        incident=incident_repo.build_summaries(db, [row])[0],
    )


@router.post("/incidents/{incident_id}/location/confirm", response_model=LocationOut)
def confirm_incident_location(
    incident_id: uuid.UUID, body: LocationConfirmRequest, auth: Editor, db: DbSession, settings: AppSettings
) -> LocationOut:
    incident, lat, lng = editorial.confirm_location(
        db,
        auth.user,
        incident_id,
        action=body.action,
        candidate_index=body.candidate_index,
        latitude=body.latitude,
        longitude=body.longitude,
        precision_meters=body.precision_meters,
        note=body.note,
        radius_m=settings.blackspot_match_radius_m,
    )
    return editorial.location_out(incident, lat, lng)
