"""News-monitor queries over ``source_items``."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import ExtractionRun, Incident, IncidentEvidence, Source, SourceItem
from app.models.enums import ProcessingStatus
from app.models.intelligence import IntelligenceRecord
from app.schemas.news import (
    ExtractionRunOut,
    KeywordRelevance,
    LinkedIncident,
    NewsClassification,
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
    category: str | None = None
    record_kind: str | None = None
    received_from: datetime | None = None
    received_to: datetime | None = None
    sort: str = "received_at"
    descending: bool = True


def news_list_query(f: NewsFilters) -> Select:
    query = select(SourceItem, Source).join(Source, Source.id == SourceItem.source_id)
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
    if f.category:
        # Classified records win; before classification the keyword screen's candidate categories apply.
        by_record = select(IntelligenceRecord.id).where(
            IntelligenceRecord.source_item_id == SourceItem.id, IntelligenceRecord.primary_category == f.category
        ).exists()
        by_screen = SourceItem.source_metadata["screening"]["categories"].contains([f.category])
        query = query.where(or_(by_record, by_screen))
    if f.record_kind:
        query = query.where(
            select(IntelligenceRecord.id).where(
                IntelligenceRecord.source_item_id == SourceItem.id, IntelligenceRecord.record_kind == f.record_kind
            ).exists()
        )
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


def _classification_status(item: SourceItem, record: IntelligenceRecord | None, linked: int) -> str:
    if record is not None:
        return "classified"
    state = item.processing_status
    if state == ProcessingStatus.PENDING:
        return "unscreened"
    if state == ProcessingStatus.FILTERED:
        return "filtered"
    if state in (ProcessingStatus.FAILED, ProcessingStatus.FETCH_FAILED):
        return "failed"
    if state == ProcessingStatus.DISCARDED:
        return "not_relevant"
    if state == ProcessingStatus.PROCESSED:
        return "classified" if linked else "not_relevant"  # pre-expansion items that became incidents
    return "awaiting_classification"


def _classification(item: SourceItem, record: IntelligenceRecord | None, linked: int) -> NewsClassification:
    screening = (item.source_metadata or {}).get("screening") or {}
    categories = screening.get("categories")
    return NewsClassification(
        status=_classification_status(item, record, linked),
        primary_category=record.primary_category if record else None,
        primary_subtype=record.primary_subtype if record else None,
        candidate_categories=[c for c in categories if isinstance(c, str)] if isinstance(categories, list) else [],
        record_kind=record.record_kind if record else None,
        geographic_scope=record.geographic_scope if record else None,
        geographic_relevance=screening.get("geographical_relevance"),
        editorial_status=record.status if record else None,
        intelligence_record_id=record.id if record else None,
        linked_incident_id=record.incident_id if record else None,
    )


def _records_for(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, IntelligenceRecord]:
    if not ids:
        return {}
    rows = session.scalars(
        select(IntelligenceRecord).where(IntelligenceRecord.source_item_id.in_(ids))
        .order_by(IntelligenceRecord.source_item_id, IntelligenceRecord.created_at.desc())
        .distinct(IntelligenceRecord.source_item_id)
    )
    return {r.source_item_id: r for r in rows}


def _summary(
    item: SourceItem, source: Source, run: ExtractionRun | None, linked: int,
    record: IntelligenceRecord | None = None,
) -> dict[str, Any]:
    return dict(
        id=item.id,
        source_id=item.source_id,
        publisher=source.name,
        source_kind=source.kind,
        headline=item.title_redacted,
        source_url=item.canonical_url,
        published_at=item.published_at,
        ingested_at=item.received_at,
        keyword_relevance=relevance(item),
        fetch_status=item.fetch_status,
        processing_status=item.processing_status,
        extraction_status=run.status if run else None,
        linked_incident_count=linked,
        source_platform=(item.source_metadata or {}).get("platform") or source.kind,
        classification=_classification(item, record, linked),
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
    records = _records_for(session, ids)
    return [
        NewsItemSummary(**_summary(item, source, runs.get(item.id), counts.get(item.id, 0), records.get(item.id)))
        for item, source in rows
    ]


def get_item_row(session: Session, item_id: uuid.UUID) -> Any | None:
    return session.execute(
        select(SourceItem, Source)
        .join(Source, Source.id == SourceItem.source_id)
        .where(SourceItem.id == item_id)
    ).first()


def build_detail(session: Session, row: Any) -> NewsItemDetail:
    item, source = row
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
        **_summary(item, source, run, len(linked_rows), _records_for(session, [item.id]).get(item.id)),
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
