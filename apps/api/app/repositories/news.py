"""News-monitor queries over ``source_items``."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import ExtractionRun, Incident, IncidentEvidence, Source, SourceItem
from app.models.enums import ProcessingStatus
from app.schemas.news import (
    ExtractionRunOut,
    KeywordRelevance,
    LinkedIncident,
    NewsItemDetail,
    NewsItemSummary,
)
from app.repositories.incidents import _like

# Statuses that mean "the keyword screen has run and let this item through".
NOT_SCREENED = (ProcessingStatus.PENDING.value, ProcessingStatus.FILTERED.value)

SORT_COLUMNS = {"received_at": SourceItem.received_at, "published_at": SourceItem.published_at}


@dataclass
class NewsFilters:
    q: str | None = None
    source_id: uuid.UUID | None = None
    processing_status: str | None = None
    relevant: bool | None = None
    has_incident: bool | None = None
    received_from: datetime | None = None
    received_to: datetime | None = None
    sort: str = "received_at"
    descending: bool = True


def news_list_query(f: NewsFilters) -> Select:
    query = select(SourceItem, Source.name).join(Source, Source.id == SourceItem.source_id)
    if f.q:
        query = query.where(SourceItem.title_redacted.ilike(_like(f.q.strip())))
    if f.source_id:
        query = query.where(SourceItem.source_id == f.source_id)
    if f.processing_status:
        query = query.where(SourceItem.processing_status == f.processing_status)
    if f.relevant is True:
        query = query.where(SourceItem.processing_status.not_in(NOT_SCREENED))
    elif f.relevant is False:
        query = query.where(SourceItem.processing_status == ProcessingStatus.FILTERED.value)
    if f.has_incident is not None:
        linked = select(IncidentEvidence.id).where(IncidentEvidence.source_item_id == SourceItem.id).exists()
        query = query.where(linked if f.has_incident else ~linked)
    if f.received_from:
        query = query.where(SourceItem.received_at >= f.received_from)
    if f.received_to:
        query = query.where(SourceItem.received_at < f.received_to)
    column = SORT_COLUMNS.get(f.sort, SourceItem.received_at)
    ordered = column.desc().nulls_last() if f.descending else column.asc().nulls_last()
    return query.order_by(ordered, SourceItem.id)


def relevance(item: SourceItem) -> KeywordRelevance:
    if item.processing_status == ProcessingStatus.PENDING:
        return KeywordRelevance(relevant=None, reason=None)
    return KeywordRelevance(
        relevant=item.processing_status != ProcessingStatus.FILTERED, reason=item.screen_reason
    )


def _latest_runs(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, ExtractionRun]:
    if not ids:
        return {}
    runs = session.scalars(
        select(ExtractionRun)
        .where(ExtractionRun.source_item_id.in_(ids))
        .order_by(ExtractionRun.source_item_id, ExtractionRun.created_at.desc())
        .distinct(ExtractionRun.source_item_id)
    )
    return {r.source_item_id: r for r in runs}


def _summary(item: SourceItem, publisher: str, run: ExtractionRun | None, linked: int) -> dict[str, Any]:
    return dict(
        id=item.id,
        source_id=item.source_id,
        publisher=publisher,
        headline=item.title_redacted,
        source_url=item.canonical_url,
        published_at=item.published_at,
        ingested_at=item.received_at,
        keyword_relevance=relevance(item),
        fetch_status=item.fetch_status,
        processing_status=item.processing_status,
        extraction_status=run.status if run else None,
        linked_incident_count=linked,
    )


def build_summaries(session: Session, rows: list[Any]) -> list[NewsItemSummary]:
    ids = [r[0].id for r in rows]
    runs = _latest_runs(session, ids)
    counts: dict[uuid.UUID, int] = {}
    if ids:
        counts = dict(
            session.execute(
                select(IncidentEvidence.source_item_id, func.count())
                .where(IncidentEvidence.source_item_id.in_(ids))
                .group_by(IncidentEvidence.source_item_id)
            ).all()
        )
    return [
        NewsItemSummary(**_summary(item, publisher, runs.get(item.id), counts.get(item.id, 0)))
        for item, publisher in rows
    ]


def get_item_row(session: Session, item_id: uuid.UUID) -> Any | None:
    return session.execute(
        select(SourceItem, Source.name)
        .join(Source, Source.id == SourceItem.source_id)
        .where(SourceItem.id == item_id)
    ).first()


def build_detail(session: Session, row: Any) -> NewsItemDetail:
    item, publisher = row
    run = _latest_runs(session, [item.id]).get(item.id)
    linked_rows = session.execute(
        select(Incident, IncidentEvidence.evidence_role)
        .join(IncidentEvidence, IncidentEvidence.incident_id == Incident.id)
        .where(IncidentEvidence.source_item_id == item.id)
        .order_by(Incident.created_at.desc(), Incident.id)
    ).all()
    extraction = None
    if run is not None:
        extraction = ExtractionRunOut(
            id=run.id,
            status=run.status,
            model_name=run.model_name,
            prompt_version=run.prompt_version,
            extraction_confidence=run.extraction_confidence,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            error_message=run.error_message,
            created_at=run.created_at,
            completed_at=run.completed_at,
            output=run.extraction_output if run.status == "succeeded" else None,
        )
    return NewsItemDetail(
        **_summary(item, publisher, run, len(linked_rows)),
        excerpt=item.excerpt_redacted,
        article_text=item.article_text_redacted,
        fetch_error=item.fetch_error,
        fetched_at=item.fetched_at,
        extraction=extraction,
        incidents=[
            LinkedIncident(
                id=i.id,
                reference_code=i.reference_code,
                incident_type=i.incident_type,
                status=i.status,
                evidence_role=role,
            )
            for i, role in linked_rows
        ],
    )
