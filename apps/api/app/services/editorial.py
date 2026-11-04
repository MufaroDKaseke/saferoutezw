"""The human editorial workflow: bulletin versions, decisions and location confirmation.

Every function takes the *authenticated* user, locks the incident row for the duration of
the transaction (so concurrent editors are serialised) and writes an audit event. The
database triggers (append-only history, human reviewer, approval before ``approved``,
latest-version approval) stay in place as the last line of defence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError, conflict, forbidden, not_found
from app.models import BulletinVersion, EditorialReview, Incident, User
from app.models.enums import (
    REVIEWER_ROLES,
    IncidentStatus,
    LocationStatus,
    ReviewDecision,
)
from app.repositories.incidents import get_incident_row
from app.schemas.location import LocationOut, build_location
from app.services.audit import record_audit
from app.services.blackspot_matching import recompute_matches
from app.services.geolocation import ZW_LAT_RANGE, ZW_LNG_RANGE
from app.services.redaction import redact

REVIEWABLE = (IncidentStatus.CANDIDATE.value, IncidentStatus.UNDER_REVIEW.value)
EDITABLE = (*REVIEWABLE, IncidentStatus.APPROVED.value)
# Direct identifiers that must never appear in a public bulletin. (Names are left to the editor.)
BLOCKED_PERSONAL_DATA = ("email", "phone", "national_id", "plate")


def _lock_incident(session: Session, incident_id: uuid.UUID) -> Incident:
    incident = session.get(Incident, incident_id, with_for_update=True, populate_existing=True)
    if incident is None:
        raise not_found("INCIDENT_NOT_FOUND", "The requested incident was not found.")
    return incident


def _require_editor(user: User) -> None:
    if not user.is_active or user.role not in {r.value for r in REVIEWER_ROLES}:
        raise forbidden("Only an active editor or admin can do this.")


def latest_version(session: Session, incident_id: uuid.UUID) -> BulletinVersion | None:
    return session.scalar(
        select(BulletinVersion)
        .where(BulletinVersion.incident_id == incident_id)
        .order_by(BulletinVersion.version_number.desc())
        .limit(1)
    )


def check_no_personal_data(headline: str, body: str) -> None:
    counts = redact(f"{headline}\n{body}").counts
    found = sorted(k for k in BLOCKED_PERSONAL_DATA if counts.get(k))
    if found:
        raise ApiError(
            422,
            "BULLETIN_CONTAINS_PERSONAL_DATA",
            "The bulletin contains personal details that must be removed before saving.",
            details=[{"field": "body", "message": f"Remove: {', '.join(found)}"}],
        )


def save_bulletin(
    session: Session, user: User, incident_id: uuid.UUID, headline: str, body: str, base_version: int | None
) -> tuple[BulletinVersion, Incident]:
    """Append a new bulletin version. Older versions are never changed."""
    _require_editor(user)
    check_no_personal_data(headline, body)
    incident = _lock_incident(session, incident_id)
    if incident.status not in EDITABLE:
        raise conflict("INCIDENT_NOT_EDITABLE", f"A {incident.status} incident cannot be edited.")

    current = latest_version(session, incident.id)
    current_number = current.version_number if current else None
    if base_version != current_number:
        raise conflict(
            "BULLETIN_VERSION_CONFLICT",
            "Someone else saved a newer version. Reload before saving your changes.",
        )

    version = BulletinVersion(
        incident_id=incident.id,
        version_number=(current_number or 0) + 1,
        headline=headline,
        body=body,
        created_by=user.id,
    )
    session.add(version)
    reopened = incident.status == IncidentStatus.APPROVED
    # A revision (or the first draft) puts the incident back in front of an editor:
    # an earlier approval never covers text it did not review.
    incident.status = IncidentStatus.UNDER_REVIEW.value
    session.flush()
    record_audit(
        session,
        actor_id=user.id,
        action="bulletin.version_saved",
        entity_type="incident",
        entity_id=incident.id,
        details={"version": version.version_number, "reopened_after_approval": reopened},
    )
    session.commit()
    return version, incident


_STATUS_FOR = {
    ReviewDecision.APPROVED: IncidentStatus.APPROVED.value,
    ReviewDecision.REJECTED: IncidentStatus.REJECTED.value,
    ReviewDecision.NEEDS_CHANGES: IncidentStatus.UNDER_REVIEW.value,
}


def record_review(
    session: Session,
    user: User,
    incident_id: uuid.UUID,
    decision: ReviewDecision,
    bulletin_version_id: uuid.UUID | None,
    notes: str | None,
) -> tuple[EditorialReview, Incident]:
    """Record an approve / reject / needs-changes decision by ``user`` on one bulletin version."""
    _require_editor(user)  # 1. the authenticated editor
    incident = _lock_incident(session, incident_id)
    if incident.status not in REVIEWABLE:  # 2. the incident's current state
        raise conflict("INCIDENT_NOT_REVIEWABLE", f"A {incident.status} incident cannot be reviewed.")

    latest = latest_version(session, incident.id)
    version: BulletinVersion | None = None
    if bulletin_version_id is not None:
        version = session.get(BulletinVersion, bulletin_version_id)
        if version is None:  # 3. the version exists
            raise not_found("BULLETIN_VERSION_NOT_FOUND", "The bulletin version was not found.")
        if version.incident_id != incident.id:  # 4. ... and belongs to this incident
            raise ApiError(422, "BULLETIN_VERSION_MISMATCH", "That bulletin version belongs to another incident.")
        if latest is None or version.id != latest.id:  # 5. ... and is still the one being decided on
            raise conflict(
                "STALE_BULLETIN_VERSION",
                "A newer bulletin version exists. Review the latest version before deciding.",
            )
    elif latest is not None and decision != ReviewDecision.APPROVED:
        version = latest  # rejections and change requests default to the current text

    review = EditorialReview(
        incident_id=incident.id,
        bulletin_version_id=version.id if version else None,
        reviewer_id=user.id,  # always the session user, never taken from the request
        decision=decision.value,
        notes=(notes or "").strip() or None,
    )
    session.add(review)
    try:
        session.flush()  # the database triggers re-check reviewer role and version freshness
        incident.status = _STATUS_FOR[decision]
        session.flush()
    except IntegrityError:
        session.rollback()
        raise conflict("DECISION_BLOCKED", "The decision was blocked by an editorial safeguard.") from None
    record_audit(
        session,
        actor_id=user.id,
        action=f"review.{decision.value}",
        entity_type="incident",
        entity_id=incident.id,
        details={
            "review_id": str(review.id),
            "version": version.version_number if version else None,
            "location_status": incident.location_status,
        },
    )
    session.commit()
    return review, incident


def confirm_location(
    session: Session,
    user: User,
    incident_id: uuid.UUID,
    *,
    action: str,
    candidate_index: int | None,
    latitude: float | None,
    longitude: float | None,
    precision_meters: float | None,
    note: str | None,
    radius_m: float,
) -> tuple[Incident, float | None, float | None]:
    """An editor accepts a proposal, picks a candidate, supplies coordinates or marks it unresolved."""
    _require_editor(user)
    incident = _lock_incident(session, incident_id)
    if incident.status not in REVIEWABLE:
        raise conflict(
            "INCIDENT_NOT_EDITABLE",
            "The location of a decided incident is fixed. Save a new bulletin version to reopen it.",
        )

    now = datetime.now(UTC)
    if action == "accept_proposed":
        if incident.location_status != LocationStatus.RESOLVED or incident.geom is None:
            raise conflict("NO_PROPOSED_LOCATION", "There is no proposed location to accept.")
        incident.location_status = LocationStatus.EDITOR_CONFIRMED.value
    elif action == "select_candidate":
        candidates = incident.location_candidates or []
        if candidate_index is None or candidate_index >= len(candidates):
            raise ApiError(422, "INVALID_CANDIDATE", "That candidate does not exist.")
        chosen = candidates[candidate_index]
        incident.geom = WKTElement(f"POINT({chosen['longitude']} {chosen['latitude']})", srid=4326)
        incident.location_status = LocationStatus.EDITOR_CONFIRMED.value
        incident.location_precision_m = chosen.get("precision_meters")
        incident.location_source = chosen.get("source")
        incident.location_method = "editor_selected_candidate"
    elif action == "set_coordinates":
        assert latitude is not None and longitude is not None
        if not (ZW_LAT_RANGE[0] <= latitude <= ZW_LAT_RANGE[1] and ZW_LNG_RANGE[0] <= longitude <= ZW_LNG_RANGE[1]):
            raise ApiError(422, "OUTSIDE_ZIMBABWE", "Those coordinates are outside Zimbabwe.")
        incident.geom = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
        incident.location_status = LocationStatus.EDITOR_CONFIRMED.value
        incident.location_precision_m = precision_meters
        incident.location_source = "Editor"
        incident.location_method = "editor_supplied_coordinates"
    else:  # mark_unresolved
        incident.geom = None
        incident.location_status = LocationStatus.UNRESOLVED.value
        incident.location_precision_m = None
        incident.location_method = "editor_marked_unresolved"

    confirmed = incident.location_status == LocationStatus.EDITOR_CONFIRMED
    incident.location_confirmed_by = user.id if confirmed else None
    incident.location_confirmed_at = now if confirmed else None
    incident.location_updated_at = now
    incident.location_note = (note or "").strip() or None
    session.flush()
    recompute_matches(session, incident, radius_m)
    record_audit(
        session,
        actor_id=user.id,
        action="incident.location_confirmed" if confirmed else "incident.location_unresolved",
        entity_type="incident",
        entity_id=incident.id,
        details={"action": action, "status": incident.location_status},
    )
    session.commit()
    row = get_incident_row(session, incident.id)
    return row[0], row[1], row[2]


def location_out(incident: Incident, lat: float | None, lng: float | None) -> LocationOut:
    return build_location(incident, lat, lng)
