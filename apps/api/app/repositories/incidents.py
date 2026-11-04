"""Incident queries. Each list endpoint uses a fixed number of queries (no N+1)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Select, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Blackspot,
    BulletinVersion,
    EditorialReview,
    ExtractionRun,
    Incident,
    IncidentEvidence,
    Source,
    SourceItem,
)
from app.models.enums import (
    EvidenceRole,
    ExtractionStatus,
    IncidentStatus,
    ReviewDecision,
)
from app.schemas.incident import (
    Assessments,
    EvidenceOut,
    EvidenceSource,
    ExtractedFacts,
    IncidentDetail,
    IncidentSummary,
    ReviewState,
)
from app.schemas.location import build_location

LAT = func.ST_Y(cast(Incident.geom, Geometry)).label("lat")
LNG = func.ST_X(cast(Incident.geom, Geometry)).label("lng")

SORT_COLUMNS = {
    "created_at": Incident.created_at,
    "occurred_at": Incident.occurred_at,
    "credibility_score": Incident.credibility_score,
    "geographic_risk_score": Incident.geographic_risk_score,
}


@dataclass
class IncidentFilters:
    status: str | None = None
    incident_type: str | None = None
    severity: str | None = None
    review_priority: str | None = None
    location_status: str | None = None
    q: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    sort: str = "created_at"
    descending: bool = True


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def incident_list_query(f: IncidentFilters) -> Select:
    query = select(Incident, LAT, LNG)
    if f.status:
        query = query.where(Incident.status == f.status)
    if f.incident_type:
        query = query.where(Incident.incident_type == f.incident_type)
    if f.severity:
        query = query.where(Incident.severity == f.severity)
    if f.review_priority:
        query = query.where(Incident.review_priority == f.review_priority)
    if f.location_status:
        query = query.where(Incident.location_status == f.location_status)
    if f.q:
        pattern = _like(f.q.strip())
        query = query.where(
            or_(Incident.reference_code.ilike(pattern), Incident.location_text.ilike(pattern))
        )
    if f.created_from:
        query = query.where(Incident.created_at >= f.created_from)
    if f.created_to:
        query = query.where(Incident.created_at < f.created_to)
    column = SORT_COLUMNS.get(f.sort, Incident.created_at)
    ordered = column.desc().nulls_last() if f.descending else column.asc().nulls_last()
    return query.order_by(ordered, Incident.id)


@dataclass
class IncidentExtras:
    source_count: int = 0
    latest_version: int | None = None
    latest_version_at: datetime | None = None
    latest_decision: str | None = None
    latest_decision_at: datetime | None = None
    extraction: ExtractionRun | None = None


def load_extras(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, IncidentExtras]:
    """Four small queries for the whole page, regardless of its size."""
    extras = {i: IncidentExtras() for i in ids}
    if not ids:
        return extras

    for incident_id, count in session.execute(
        select(IncidentEvidence.incident_id, func.count())
        .where(IncidentEvidence.incident_id.in_(ids))
        .group_by(IncidentEvidence.incident_id)
    ):
        extras[incident_id].source_count = count

    for incident_id, version, created_at in session.execute(
        select(BulletinVersion.incident_id, BulletinVersion.version_number, BulletinVersion.created_at)
        .where(BulletinVersion.incident_id.in_(ids))
        .order_by(BulletinVersion.incident_id, BulletinVersion.version_number.desc())
        .distinct(BulletinVersion.incident_id)
    ):
        extras[incident_id].latest_version = version
        extras[incident_id].latest_version_at = created_at

    for incident_id, decision, reviewed_at in session.execute(
        select(EditorialReview.incident_id, EditorialReview.decision, EditorialReview.reviewed_at)
        .where(EditorialReview.incident_id.in_(ids))
        .order_by(EditorialReview.incident_id, EditorialReview.reviewed_at.desc())
        .distinct(EditorialReview.incident_id)
    ):
        extras[incident_id].latest_decision = decision
        extras[incident_id].latest_decision_at = reviewed_at

    for incident_id, run in session.execute(
        select(IncidentEvidence.incident_id, ExtractionRun)
        .join(ExtractionRun, ExtractionRun.source_item_id == IncidentEvidence.source_item_id)
        .where(
            IncidentEvidence.incident_id.in_(ids),
            IncidentEvidence.evidence_role == EvidenceRole.PRIMARY.value,
            ExtractionRun.status == ExtractionStatus.SUCCEEDED.value,
        )
        .order_by(IncidentEvidence.incident_id, ExtractionRun.created_at.desc())
        .distinct(IncidentEvidence.incident_id)
    ):
        extras[incident_id].extraction = run
    return extras


def derive_review_state(status: str, extras: IncidentExtras) -> ReviewState:
    if status in (IncidentStatus.APPROVED, IncidentStatus.PUBLISHED):
        return "approved"
    if status == IncidentStatus.REJECTED:
        return "rejected"
    if status == IncidentStatus.ARCHIVED:
        return "archived"
    if extras.latest_decision == ReviewDecision.NEEDS_CHANGES:
        # A draft saved after the request for changes counts as a resubmission.
        newer_draft = (
            extras.latest_version_at is not None
            and extras.latest_decision_at is not None
            and extras.latest_version_at > extras.latest_decision_at
        )
        if not newer_draft:
            return "needs_changes"
    return "pending_review"


def _summary_text(extras: IncidentExtras) -> str | None:
    if extras.extraction is None:
        return None
    value = (extras.extraction.extraction_output or {}).get("summary")
    return value if isinstance(value, str) and value.strip() else None


def build_summary(row: Any, extras: IncidentExtras) -> IncidentSummary:
    incident: Incident = row[0]
    lat, lng = row[1], row[2]
    facts = _facts(extras.extraction)
    return IncidentSummary(
        id=incident.id,
        reference_code=incident.reference_code,
        incident_type=incident.incident_type,
        severity=incident.severity,
        status=incident.status,
        review_state=derive_review_state(incident.status, extras),
        review_priority=incident.review_priority,
        summary=_summary_text(extras),
        location_text=incident.location_text,
        location_status=incident.location_status,
        has_coordinates=lat is not None and lng is not None,
        occurred_at=incident.occurred_at,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        source_count=extras.source_count,
        credibility_score=incident.credibility_score,
        geographic_risk_score=incident.geographic_risk_score,
        latest_bulletin_version=extras.latest_version,
        extraction_confidence=facts.extraction_confidence if facts else None,
        missing_information_count=len(missing_information(incident, facts)),
    )


def build_summaries(session: Session, rows: list[Any]) -> list[IncidentSummary]:
    extras = load_extras(session, [r[0].id for r in rows])
    return [build_summary(r, extras[r[0].id]) for r in rows]


def get_incident_row(session: Session, incident_id: uuid.UUID) -> Any | None:
    return session.execute(select(Incident, LAT, LNG).where(Incident.id == incident_id)).first()


def _facts(run: ExtractionRun | None) -> ExtractedFacts | None:
    if run is None:
        return None
    out = run.extraction_output or {}

    def number(key: str) -> int | None:
        value = out.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def text(key: str) -> str | None:
        value = out.get(key)
        return value if isinstance(value, str) and value.strip() else None

    quotes = out.get("evidence_quotes")
    return ExtractedFacts(
        summary=text("summary"),
        cause=text("cause"),
        fatalities=number("fatalities"),
        injuries=number("injuries"),
        vehicles_involved=number("vehicles_involved"),
        evidence_quotes=[q for q in quotes if isinstance(q, str)] if isinstance(quotes, list) else [],
        extraction_confidence=run.extraction_confidence,
        model_name=run.model_name,
        prompt_version=run.prompt_version,
    )


def missing_information(incident: Incident, facts: ExtractedFacts | None) -> list[str]:
    """Plain-language gaps an editor should look at before approving."""
    gaps: list[str] = []
    if incident.location_status not in ("resolved", "editor_confirmed"):
        gaps.append("Exact location")
    if incident.occurred_at is None:
        gaps.append("Time of incident")
    if facts is None:
        gaps.append("AI extraction")
        return gaps
    if facts.fatalities is None and facts.injuries is None:
        gaps.append("Casualty numbers")
    if facts.vehicles_involved is None:
        gaps.append("Vehicles involved")
    if facts.cause is None:
        gaps.append("Cause")
    return gaps


def build_detail(session: Session, row: Any) -> IncidentDetail:
    incident: Incident = row[0]
    extras = load_extras(session, [incident.id])[incident.id]
    base = build_summary(row, extras)
    facts = _facts(extras.extraction)
    has_blackspots = bool(session.scalar(select(exists().where(Blackspot.id.is_not(None)))))
    return IncidentDetail(
        **base.model_dump(),
        assessments=Assessments(
            credibility_score=incident.credibility_score,
            geographic_risk_score=incident.geographic_risk_score,
            extraction_confidence=facts.extraction_confidence if facts else None,
            review_priority=incident.review_priority,
            blackspot_data="available" if has_blackspots else "unavailable",
        ),
        extracted_facts=facts,
        missing_information=missing_information(incident, facts),
        location=build_location(incident, row[1], row[2]),
    )


def evidence_query(incident_id: uuid.UUID) -> Select:
    return (
        select(IncidentEvidence, SourceItem, Source)
        .join(SourceItem, SourceItem.id == IncidentEvidence.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(IncidentEvidence.incident_id == incident_id)
        .order_by(IncidentEvidence.created_at, IncidentEvidence.id)
    )


def build_evidence(session: Session, rows: list[Any]) -> list[EvidenceOut]:
    item_ids = [r[1].id for r in rows]
    latest: dict[uuid.UUID, ExtractionRun] = {}
    if item_ids:
        for run in session.scalars(
            select(ExtractionRun)
            .where(ExtractionRun.source_item_id.in_(item_ids))
            .order_by(ExtractionRun.source_item_id, ExtractionRun.created_at.desc())
            .distinct(ExtractionRun.source_item_id)
        ):
            latest[run.source_item_id] = run
    out = []
    for evidence, item, source in rows:
        run = latest.get(item.id)
        out.append(
            EvidenceOut(
                id=evidence.id,
                role=evidence.evidence_role,
                created_at=evidence.created_at,
                source_item=EvidenceSource(
                    id=item.id,
                    publisher=source.name,
                    verification_tier=source.verification_tier,
                    headline=item.title_redacted,
                    source_url=item.canonical_url,
                    published_at=item.published_at,
                    received_at=item.received_at,
                ),
                extraction_status=run.status if run else None,
                extraction_confidence=run.extraction_confidence if run else None,
                extraction_output=run.extraction_output if run and run.status == "succeeded" else None,
            )
        )
    return out
