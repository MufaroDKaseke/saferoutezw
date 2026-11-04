"""Explicit human publication of an approved bulletin version.

Approval and publication are separate acts. Approving never publishes; an authorised editor
must publish the exact approved (and still latest) version. Everything runs in one
transaction with the incident row locked; the ``public_alerts`` database trigger re-checks the
approval as the last line of defence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError, conflict, not_found
from app.models import BulletinVersion, EditorialReview, Incident, PublicAlert, User
from app.models.enums import AlertStatus, IncidentStatus, ReviewDecision
from app.services.audit import record_audit
from app.services.editorial import (
    _lock_incident,
    _require_editor,
    check_no_personal_data,
    latest_version,
)
from app.services.zimbabwe import detect_province, normalise_province


def _approving_review(session: Session, incident_id: uuid.UUID, version_id: uuid.UUID) -> EditorialReview | None:
    """The newest decision on this version, if (and only if) it is an approval."""
    newest = session.scalar(
        select(EditorialReview)
        .where(EditorialReview.incident_id == incident_id, EditorialReview.bulletin_version_id == version_id)
        .order_by(EditorialReview.reviewed_at.desc(), EditorialReview.id.desc())
        .limit(1)
    )
    if newest is None or newest.decision != ReviewDecision.APPROVED.value:
        return None
    return newest


def publish_alert(
    session: Session,
    user: User,
    incident_id: uuid.UUID,
    bulletin_version_id: uuid.UUID,
    *,
    province: str | None = None,
    road_name: str | None = None,
) -> PublicAlert:
    _require_editor(user)
    incident = _lock_incident(session, incident_id)
    if incident.status == IncidentStatus.PUBLISHED:
        raise conflict("ALREADY_PUBLISHED", "This incident is already published. Unpublish it first.")
    if incident.status != IncidentStatus.APPROVED:
        raise conflict("INCIDENT_NOT_APPROVED", "Only an approved incident can be published.")

    version = session.get(BulletinVersion, bulletin_version_id)
    if version is None:
        raise not_found("BULLETIN_VERSION_NOT_FOUND", "The bulletin version was not found.")
    if version.incident_id != incident.id:
        raise ApiError(422, "BULLETIN_VERSION_MISMATCH", "That bulletin version belongs to another incident.")
    latest = latest_version(session, incident.id)
    if latest is None or latest.id != version.id:
        raise conflict(
            "STALE_BULLETIN_VERSION",
            "A newer bulletin version exists. It needs its own approval before it can be published.",
        )
    review = _approving_review(session, incident.id, version.id)
    if review is None:
        raise conflict("NO_VALID_APPROVAL", "This bulletin version has no standing editorial approval.")
    check_no_personal_data(version.headline, version.body)

    chosen_province = normalise_province(province) if province else None
    if province and chosen_province is None:
        raise ApiError(422, "INVALID_PROVINCE", "That is not a Zimbabwe province.")
    chosen_province = chosen_province or detect_province(incident.location_text)
    chosen_road = (road_name or "").strip() or None

    now = datetime.now(UTC)
    alert = session.scalar(select(PublicAlert).where(PublicAlert.bulletin_version_id == version.id))
    if alert is None:
        alert = PublicAlert(
            incident_id=incident.id,
            bulletin_version_id=version.id,
            approval_review_id=review.id,
        )
        session.add(alert)
    elif alert.approval_review_id != review.id:
        raise conflict("APPROVAL_CHANGED", "The approval on record for this version changed. Reload and retry.")
    alert.status = AlertStatus.PUBLISHED.value
    alert.published_at = now
    alert.withdrawn_at = None
    alert.province = chosen_province
    alert.road_name = chosen_road
    incident.status = IncidentStatus.PUBLISHED.value
    try:
        session.flush()  # the public_alerts trigger re-validates the human approval here
    except IntegrityError:
        session.rollback()
        raise conflict("PUBLICATION_BLOCKED", "Publication was blocked by an editorial safeguard.") from None
    record_audit(
        session,
        actor_id=user.id,
        action="alert.published",
        entity_type="incident",
        entity_id=incident.id,
        details={
            "alert_id": str(alert.id),
            "bulletin_version_id": str(version.id),
            "version": version.version_number,
            "review_id": str(review.id),
        },
    )
    session.commit()
    return alert


def unpublish_alert(session: Session, user: User, incident_id: uuid.UUID, reason: str | None) -> PublicAlert:
    _require_editor(user)
    incident: Incident = _lock_incident(session, incident_id)
    alert = session.scalar(
        select(PublicAlert).where(
            PublicAlert.incident_id == incident.id, PublicAlert.status == AlertStatus.PUBLISHED.value
        )
    )
    if alert is None:
        raise conflict("NOT_PUBLISHED", "This incident has no published alert.")
    alert.status = AlertStatus.WITHDRAWN.value
    alert.withdrawn_at = datetime.now(UTC)
    incident.status = IncidentStatus.APPROVED.value  # approval stands; publication does not
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise conflict("UNPUBLISH_BLOCKED", "Withdrawal was blocked by an editorial safeguard.") from None
    record_audit(
        session,
        actor_id=user.id,
        action="alert.unpublished",
        entity_type="incident",
        entity_id=incident.id,
        details={"alert_id": str(alert.id), "reason": (reason or "").strip()[:500] or None},
    )
    session.commit()
    return alert
