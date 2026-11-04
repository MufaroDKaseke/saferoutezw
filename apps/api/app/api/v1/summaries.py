"""AI draft summary for the editorial workspace. Returns text only: nothing is saved or published."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AppSettings, DbSession, Editor
from app.api.errors import ERROR_RESPONSES, ApiError, not_found
from app.models import Incident, IncidentEvidence, Source, SourceItem
from app.models.enums import EvidenceRole
from app.schemas.common import ApiModel
from app.services import summarise as svc
from app.services.audit import record_audit

router = APIRouter(tags=["editorial"], responses=ERROR_RESPONSES)

ROLE_ORDER = {
    EvidenceRole.PRIMARY.value: 0,
    EvidenceRole.CORROBORATING.value: 1,
    EvidenceRole.CONTEXT.value: 2,
}


class SummaryDraft(ApiModel):
    summary: str
    model: str
    sources_used: int
    notice: str


def get_summariser(settings: AppSettings) -> svc.Summariser:
    try:
        return svc.OpenAISummariser.from_settings(settings)
    except svc.SummariserUnavailable:
        raise ApiError(503, "AI_UNAVAILABLE", "AI summaries are not configured (OPENAI_API_KEY).") from None


def _sources(db: Session, incident_id: uuid.UUID) -> list[svc.SourceText]:
    rows = db.execute(
        select(IncidentEvidence.evidence_role, Source.name, SourceItem)
        .join(SourceItem, SourceItem.id == IncidentEvidence.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(
            IncidentEvidence.incident_id == incident_id,
            IncidentEvidence.evidence_role != EvidenceRole.CONTRADICTING.value,
        )
    ).all()
    ordered = sorted(rows, key=lambda r: ROLE_ORDER.get(r[0], 9))
    out: list[svc.SourceText] = []
    for _role, name, item in ordered:
        text = item.article_text_redacted or item.excerpt_redacted or item.title_redacted
        if text:
            out.append(svc.SourceText(source_name=name, title=item.title_redacted, text=text))
    return out[: svc.MAX_SOURCES]


@router.post("/incidents/{incident_id}/summary", response_model=SummaryDraft)
def generate_incident_summary(
    incident_id: uuid.UUID,
    auth: Editor,
    db: DbSession,
    summariser: Annotated[svc.Summariser, Depends(get_summariser)],
) -> SummaryDraft:
    """Draft a public summary of the whole story from its redacted sources. The editor must review it."""
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise not_found("INCIDENT_NOT_FOUND", "The requested incident was not found.")
    sources = _sources(db, incident.id)
    if not sources:
        raise ApiError(409, "NO_SOURCE_TEXT", "This incident has no source text to summarise.")
    try:
        output = summariser.summarise(
            svc.SummaryInput(
                incident_type=incident.incident_type,
                severity=incident.severity,
                location_text=incident.location_text,
                occurred_at=incident.occurred_at,
                sources=sources,
            )
        )
        text = svc.clean_summary(output.text)
    except svc.SummariserUnavailable:
        raise ApiError(503, "AI_UNAVAILABLE", "AI summaries are not available right now.") from None
    except svc.SummaryError as exc:
        raise ApiError(502, "AI_FAILED", str(exc)) from None
    record_audit(
        db,
        actor_id=auth.user.id,
        action="incident.summary_drafted",
        entity_type="incident",
        entity_id=incident.id,
        details={"model": output.model, "sources": len(sources), "prompt": svc.PROMPT_VERSION},
    )
    db.commit()
    return SummaryDraft(
        summary=text,
        model=output.model,
        sources_used=len(sources),
        notice="AI draft. Check every fact against the sources and edit before saving. Nothing has been saved or published.",
    )
