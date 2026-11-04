"""Human editorial workflow for intelligence records (policy, statistics, projects, closures...).

Mirrors the incident bulletin workflow: every function takes the authenticated user, locks the
record row, and writes an audit event. Versions and reviews are append-only (database triggers),
an approval is bound to the exact latest version, and publication is a separate, explicit action
that picks an output type. None of this ever creates a public hazard alert; those still come only
from an approved and published incident.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError, conflict, forbidden, not_found
from app.models import User
from app.models.enums import REVIEWER_ROLES
from app.models.intelligence import (
    IntelligenceRecord,
    IntelligenceReview,
    IntelligenceVersion,
    PublicationOutput,
    StatisticalObservation,
)
from app.schemas.intelligence_api import VersionCreate
from app.services.audit import record_audit
from app.services.editorial import check_no_personal_data
from app.taxonomy import (
    ACTIONABLE_CATEGORIES,
    PublicationOutput as OutputType,
    RecordStatus,
    is_valid_subtype,
    output_allowed,
)

REVIEWABLE = (RecordStatus.CANDIDATE.value, RecordStatus.UNDER_REVIEW.value)
EDITABLE = (*REVIEWABLE, RecordStatus.APPROVED.value)


def _lock_record(session: Session, record_id: uuid.UUID) -> IntelligenceRecord:
    record = session.get(IntelligenceRecord, record_id, with_for_update=True, populate_existing=True)
    if record is None:
        raise not_found("INTELLIGENCE_NOT_FOUND", "The requested record was not found.")
    return record


def _require_editor(user: User) -> None:
    if not user.is_active or user.role not in {r.value for r in REVIEWER_ROLES}:
        raise forbidden("Only an active editor or admin can do this.")


def latest_version(session: Session, record_id: uuid.UUID) -> IntelligenceVersion | None:
    return session.scalar(
        select(IntelligenceVersion).where(IntelligenceVersion.record_id == record_id)
        .order_by(IntelligenceVersion.version_number.desc()).limit(1)
    )


def _figure_snapshot(session: Session, record_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(
        select(StatisticalObservation)
        .where(StatisticalObservation.record_id == record_id, StatisticalObservation.verification_status != "rejected")
        .order_by(StatisticalObservation.metric, StatisticalObservation.period_start.nulls_last(), StatisticalObservation.id)
    ).all()
    return [
        {
            "observation_id": str(o.id), "metric": o.metric, "value": float(o.value), "unit": o.unit,
            "period_start": o.period_start.isoformat() if o.period_start else None,
            "period_end": o.period_end.isoformat() if o.period_end else None,
            "geographic_coverage": o.geographic_coverage, "source_reference": o.source_reference,
            "methodology": o.methodology, "comparison_period": o.comparison_period,
            "is_preliminary": o.is_preliminary, "verification_status": o.verification_status,
        }
        for o in rows
    ]


def save_version(
    session: Session, user: User, record_id: uuid.UUID, body: VersionCreate
) -> IntelligenceVersion:
    """Append an editorial version (corrected classification, summary, scope, date, figures)."""
    _require_editor(user)
    check_no_personal_data(body.headline, body.summary)
    record = _lock_record(session, record_id)
    if record.status not in EDITABLE:
        raise conflict("RECORD_NOT_EDITABLE", f"A {record.status} record cannot be edited.")

    category = body.primary_category
    if body.primary_subtype is not None and not is_valid_subtype(category.value, body.primary_subtype):
        raise ApiError(422, "INVALID_SUBTYPE", "That subtype does not belong to the chosen category.",
                       details=[{"field": "primary_subtype", "message": "Choose a subtype of the category."}])
    if record.incident_id is not None and category not in ACTIONABLE_CATEGORIES:
        raise conflict("RECORD_LINKED_TO_INCIDENT",
                       "This record is linked to an incident, so it must stay an actionable category.")

    current = latest_version(session, record.id)
    current_number = current.version_number if current else None
    if body.base_version != current_number:
        raise conflict("VERSION_CONFLICT", "Someone else saved a newer version. Reload before saving your changes.")

    now = datetime.now(UTC)
    if body.figure_decisions:
        owned = {
            o.id: o for o in session.scalars(
                select(StatisticalObservation).where(StatisticalObservation.record_id == record.id)
            )
        }
        for decision in body.figure_decisions:
            obs = owned.get(decision.observation_id)
            if obs is None:
                raise ApiError(422, "FIGURE_NOT_FOUND", "A figure does not belong to this record.")
            obs.verification_status = decision.status
            obs.verified_by, obs.verified_at = (None, None) if decision.status == "unverified" else (user.id, now)

    before = {"category": record.primary_category, "subtype": record.primary_subtype, "scope": record.geographic_scope}
    session.flush()
    version = IntelligenceVersion(
        record_id=record.id, version_number=(current_number or 0) + 1, headline=body.headline,
        summary=body.summary, primary_category=category.value, primary_subtype=body.primary_subtype,
        geographic_scope=body.geographic_scope.value, event_date=body.event_date,
        figures=_figure_snapshot(session, record.id), source_attribution=body.source_attribution,
        change_note=body.change_note, created_by=user.id,
    )
    session.add(version)
    reopened = record.status == RecordStatus.APPROVED.value
    record.headline, record.neutral_summary = body.headline, body.summary
    record.primary_category, record.primary_subtype = category.value, body.primary_subtype
    record.geographic_scope, record.event_date = body.geographic_scope.value, body.event_date
    record.source_attribution = body.source_attribution
    record.status = RecordStatus.UNDER_REVIEW.value  # an earlier approval never covers unreviewed edits
    session.flush()
    record_audit(
        session, actor_id=user.id, action="intelligence.version_saved", entity_type="intelligence_record",
        entity_id=record.id,
        details={"version": version.version_number, "reopened_after_approval": reopened,
                 "before": before, "after": {"category": category.value, "subtype": body.primary_subtype,
                                             "scope": body.geographic_scope.value},
                 "figure_decisions": len(body.figure_decisions)},
    )
    session.commit()
    return version


_STATUS_FOR = {
    "approved": RecordStatus.APPROVED.value,
    "rejected": RecordStatus.REJECTED.value,
    "needs_changes": RecordStatus.UNDER_REVIEW.value,
}


def record_review(
    session: Session, user: User, record_id: uuid.UUID, decision: str, version_id: uuid.UUID | None,
    notes: str | None,
) -> IntelligenceReview:
    _require_editor(user)
    record = _lock_record(session, record_id)
    if record.status not in REVIEWABLE:
        raise conflict("RECORD_NOT_REVIEWABLE", f"A {record.status} record cannot be reviewed.")
    latest = latest_version(session, record.id)
    version: IntelligenceVersion | None = None
    if version_id is not None:
        version = session.get(IntelligenceVersion, version_id)
        if version is None:
            raise not_found("VERSION_NOT_FOUND", "The version was not found.")
        if version.record_id != record.id:
            raise ApiError(422, "VERSION_MISMATCH", "That version belongs to another record.")
        if latest is None or version.id != latest.id:
            raise conflict("STALE_VERSION", "A newer version exists. Review the latest version before deciding.")
    elif latest is not None and decision != "approved":
        version = latest

    if decision == "approved":
        if version is None:
            raise ApiError(422, "VERSION_REQUIRED", "Save an editorial version before approving.")
        pending = session.scalar(
            select(StatisticalObservation.id).where(
                StatisticalObservation.record_id == record.id, StatisticalObservation.verification_status == "unverified"
            ).limit(1)
        )
        if pending is not None:
            raise conflict("UNVERIFIED_FIGURES", "Verify or reject every extracted figure before approving.")

    review = IntelligenceReview(
        record_id=record.id, version_id=version.id if version else None, reviewer_id=user.id,
        decision=decision, notes=(notes or "").strip() or None,
    )
    session.add(review)
    try:
        session.flush()
        record.status = _STATUS_FOR[decision]
        session.flush()
    except IntegrityError:
        session.rollback()
        raise conflict("DECISION_BLOCKED", "The decision was blocked by an editorial safeguard.") from None
    record_audit(
        session, actor_id=user.id, action=f"intelligence.review.{decision}", entity_type="intelligence_record",
        entity_id=record.id,
        details={"review_id": str(review.id), "version": version.version_number if version else None},
    )
    session.commit()
    return review


def publish_output(
    session: Session, user: User, record_id: uuid.UUID, output_type: OutputType
) -> PublicationOutput:
    """Publish the latest approved version as one output type. Separate from approval."""
    _require_editor(user)
    record = _lock_record(session, record_id)
    if record.status not in (RecordStatus.APPROVED.value, RecordStatus.PUBLISHED.value):
        raise conflict("RECORD_NOT_APPROVED", f"A {record.status} record cannot be published.")
    if not output_allowed(record.primary_category, output_type.value):
        raise ApiError(422, "OUTPUT_NOT_ALLOWED",
                       f"A {record.primary_category} record cannot be published as {output_type.value}.")
    version = latest_version(session, record.id)
    newest = session.scalar(
        select(IntelligenceReview).where(IntelligenceReview.record_id == record.id)
        .order_by(IntelligenceReview.reviewed_at.desc(), IntelligenceReview.id.desc()).limit(1)
    )
    if version is None or newest is None or newest.decision != "approved" or newest.version_id != version.id:
        raise conflict("NO_STANDING_APPROVAL", "The latest version has no standing approval.")
    check_no_personal_data(version.headline, version.summary)
    if output_type is OutputType.STATISTICAL_INSIGHT:
        verified = session.scalar(
            select(StatisticalObservation.id).where(
                StatisticalObservation.record_id == record.id, StatisticalObservation.verification_status == "verified"
            ).limit(1)
        )
        if verified is None:
            raise conflict("NO_VERIFIED_FIGURES", "A statistical insight needs at least one verified figure.")

    existing = session.scalar(
        select(PublicationOutput).where(
            PublicationOutput.version_id == version.id, PublicationOutput.output_type == output_type.value
        )
    )
    try:
        if existing is not None:
            if existing.status == "published":
                raise conflict("ALREADY_PUBLISHED", "This version is already published as that output.")
            existing.status, existing.withdrawn_at = "published", None
            existing.approval_review_id, existing.published_by = newest.id, user.id
            output = existing
        else:
            output = PublicationOutput(
                record_id=record.id, version_id=version.id, approval_review_id=newest.id,
                output_type=output_type.value, published_by=user.id,
            )
            session.add(output)
        session.flush()
        record.status = RecordStatus.PUBLISHED.value
        session.flush()
    except IntegrityError:
        session.rollback()
        raise conflict("PUBLICATION_BLOCKED", "Publication was blocked by an editorial safeguard.") from None
    record_audit(
        session, actor_id=user.id, action="intelligence.published", entity_type="intelligence_record",
        entity_id=record.id,
        details={"output_id": str(output.id), "output_type": output_type.value, "version": version.version_number},
    )
    session.commit()
    return output


def withdraw_output(session: Session, user: User, output_id: uuid.UUID) -> PublicationOutput:
    _require_editor(user)
    output = session.get(PublicationOutput, output_id)
    if output is None:
        raise not_found("OUTPUT_NOT_FOUND", "The publication was not found.")
    record = _lock_record(session, output.record_id)
    if output.status != "published":
        raise conflict("NOT_PUBLISHED", "This output is not published.")
    output.status, output.withdrawn_at = "withdrawn", datetime.now(UTC)
    session.flush()
    still = session.scalar(
        select(PublicationOutput.id).where(
            PublicationOutput.record_id == record.id, PublicationOutput.status == "published"
        ).limit(1)
    )
    if still is None:
        record.status = RecordStatus.APPROVED.value
    record_audit(
        session, actor_id=user.id, action="intelligence.withdrawn", entity_type="intelligence_record",
        entity_id=record.id, details={"output_id": str(output.id), "output_type": output.output_type},
    )
    session.commit()
    return output

