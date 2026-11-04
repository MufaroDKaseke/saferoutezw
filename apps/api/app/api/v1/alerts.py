"""Newsroom view of approved bulletins as alerts, and one-click publication.

Every approved incident appears here automatically as "approved, not yet sent". Publishing is
still an explicit editor action: ``POST /alerts/{incident_id}/publish`` publishes the incident's
latest approved bulletin version (the server re-checks approval, freshness and privacy).
The alert id in this API is the incident id: an alert row only exists once published.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy import exists, false, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, Editor, Reader
from app.api.errors import ERROR_RESPONSES, conflict, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models import BulletinVersion, EditorialReview, Incident, PublicAlert, User
from app.models.enums import AlertStatus, IncidentStatus, ReviewDecision
from app.schemas.common import ApiModel, UtcDatetime
from app.services import publishing

router = APIRouter(tags=["alerts"], responses=ERROR_RESPONSES)

# The newsroom UI knows five states. Live alerts only ever are the first three: SMS/WhatsApp delivery is
# not real yet, so "publication_pending" and "delivery_failed" are accepted as filters but match nothing.
PublicationState = Literal["approved_not_published", "publication_pending", "published", "delivery_failed", "withdrawn"]
NEVER_LIVE = ("publication_pending", "delivery_failed")
LISTED = (IncidentStatus.APPROVED.value, IncidentStatus.PUBLISHED.value)


class AlertChannelOut(ApiModel):
    channel: Literal["web"]
    status: Literal["sent", "pending"]
    max_attempts: int
    last_error: str | None


class AlertOut(ApiModel):
    id: uuid.UUID  # the incident id
    reference: str
    incident_id: uuid.UUID
    incident_reference: str
    incident_type: str
    location_text: str | None
    bulletin_version_id: uuid.UUID
    bulletin_version_number: int
    headline: str
    body: str
    approval_review_id: uuid.UUID
    approved_by_name: str
    approved_at: UtcDatetime
    status: Literal["ready", "published", "withdrawn"]
    published_at: UtcDatetime | None
    publication_state: PublicationState
    channels: list[AlertChannelOut]
    public_alert_id: uuid.UUID | None


class PublishAlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    province: Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)] | None = None
    road_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)] | None = None


class UnpublishAlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


def _build(db: Session, incident: Incident) -> AlertOut | None:
    version = db.scalar(
        select(BulletinVersion)
        .where(BulletinVersion.incident_id == incident.id)
        .order_by(BulletinVersion.version_number.desc())
        .limit(1)
    )
    if version is None:
        return None
    review_row = db.execute(
        select(EditorialReview, User.display_name)
        .join(User, User.id == EditorialReview.reviewer_id)
        .where(
            EditorialReview.incident_id == incident.id,
            EditorialReview.bulletin_version_id == version.id,
            EditorialReview.decision == ReviewDecision.APPROVED.value,
        )
        .order_by(EditorialReview.reviewed_at.desc())
        .limit(1)
    ).first()
    if review_row is None:
        return None
    review, reviewer = review_row
    alert = db.scalar(select(PublicAlert).where(PublicAlert.incident_id == incident.id).order_by(PublicAlert.created_at.desc()).limit(1))

    published = alert is not None and alert.status == AlertStatus.PUBLISHED.value
    withdrawn = alert is not None and alert.status == AlertStatus.WITHDRAWN.value
    state: PublicationState = "published" if published else "withdrawn" if withdrawn else "approved_not_published"
    status = "published" if published else "withdrawn" if withdrawn else "ready"
    channels = (
        [AlertChannelOut(channel="web", status="sent", max_attempts=1, last_error=None)] if published else []
    )
    return AlertOut(
        id=incident.id,
        reference=f"A-{incident.reference_code}",
        incident_id=incident.id,
        incident_reference=incident.reference_code,
        incident_type=incident.incident_type,
        location_text=incident.location_text,
        bulletin_version_id=version.id,
        bulletin_version_number=version.version_number,
        headline=version.headline,
        body=version.body,
        approval_review_id=review.id,
        approved_by_name=reviewer,
        approved_at=review.reviewed_at,
        status=status,
        published_at=alert.published_at if published and alert else None,
        publication_state=state,
        channels=channels,
        public_alert_id=alert.id if published and alert else None,
    )


def _get(db: Session, incident_id: uuid.UUID) -> AlertOut:
    incident = db.get(Incident, incident_id)
    out = _build(db, incident) if incident is not None and incident.status in LISTED else None
    if out is None:
        raise not_found("ALERT_NOT_FOUND", "No approved alert exists for that incident.")
    return out


@router.get("/alerts", response_model=Page[AlertOut])
def list_alerts(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    search: Annotated[str | None, Query(max_length=200)] = None,
    state: PublicationState | None = None,
) -> Page[AlertOut]:
    """Approved incidents, newest approval first. Not-yet-published ones come first."""
    query = select(Incident).where(Incident.status.in_(LISTED))
    if state in NEVER_LIVE:
        query = query.where(false())
    elif state == "published":
        query = query.where(Incident.status == IncidentStatus.PUBLISHED.value)
    elif state == "withdrawn":
        query = query.where(
            Incident.status == IncidentStatus.APPROVED.value,
            exists().where(PublicAlert.incident_id == Incident.id, PublicAlert.status == AlertStatus.WITHDRAWN.value),
        )
    elif state == "approved_not_published":
        query = query.where(
            Incident.status == IncidentStatus.APPROVED.value,
            ~exists().where(PublicAlert.incident_id == Incident.id, PublicAlert.status == AlertStatus.WITHDRAWN.value),
        )
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(
            or_(
                Incident.reference_code.ilike(pattern),
                Incident.location_text.ilike(pattern),
                exists().where(BulletinVersion.incident_id == Incident.id, BulletinVersion.headline.ilike(pattern)),
            )
        )
    published_last = (Incident.status == IncidentStatus.PUBLISHED.value).asc()
    query = query.order_by(published_last, Incident.updated_at.desc(), Incident.id)
    rows, total = paginate(db, query, pagination)
    items = [item for (incident,) in rows if (item := _build(db, incident)) is not None]
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/alerts/{incident_id}", response_model=AlertOut)
def get_alert(incident_id: uuid.UUID, auth: Reader, db: DbSession) -> AlertOut:
    return _get(db, incident_id)


@router.post("/alerts/{incident_id}/publish", response_model=AlertOut)
def publish_alert_now(
    incident_id: uuid.UUID, body: PublishAlertRequest, auth: Editor, db: DbSession
) -> AlertOut:
    """One click: publish this incident's latest approved bulletin version to the public site."""
    current = _get(db, incident_id)
    if current.status == "published":
        raise conflict("ALREADY_PUBLISHED", "This alert is already published.")
    publishing.publish_alert(
        db, auth.user, incident_id, current.bulletin_version_id, province=body.province, road_name=body.road_name
    )
    return _get(db, incident_id)


@router.post("/alerts/{incident_id}/unpublish", response_model=AlertOut)
def unpublish_alert_now(
    incident_id: uuid.UUID, body: UnpublishAlertRequest, auth: Editor, db: DbSession
) -> AlertOut:
    publishing.unpublish_alert(db, auth.user, incident_id, body.reason)
    return _get(db, incident_id)
