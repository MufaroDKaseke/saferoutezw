"""One timeline over ingestion runs and AI extraction runs (UNION ALL, indexed by start time)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, Integer, Select, Text, Uuid, cast, literal, null, select
from sqlalchemy.orm import Session

from app.models import ExtractionRun, IngestionRun, Source, SourceItem
from app.schemas.processing import ProcessingRun, ProcessingRunDetail


def _null(type_):
    return cast(null(), type_)


def _union():
    ingestion = (
        select(
            IngestionRun.id.label("id"),
            literal("ingestion").label("kind"),
            IngestionRun.status.label("status"),
            IngestionRun.started_at.label("started_at"),
            IngestionRun.completed_at.label("completed_at"),
            IngestionRun.source_id.label("source_id"),
            Source.name.label("source_name"),
            _null(Uuid).label("source_item_id"),
            _null(Text).label("headline"),
            _null(Text).label("model_name"),
            _null(Text).label("prompt_version"),
            _null(Float).label("extraction_confidence"),
            _null(Integer).label("input_tokens"),
            _null(Integer).label("output_tokens"),
            IngestionRun.fetched_count.label("fetched_count"),
            IngestionRun.inserted_count.label("inserted_count"),
            IngestionRun.duplicate_count.label("duplicate_count"),
            IngestionRun.error_count.label("error_count"),
            IngestionRun.error_message.label("error_message"),
        )
        .join(Source, Source.id == IngestionRun.source_id)
    )
    extraction = (
        select(
            ExtractionRun.id,
            literal("extraction"),
            ExtractionRun.status,
            ExtractionRun.created_at,
            ExtractionRun.completed_at,
            Source.id,
            Source.name,
            SourceItem.id,
            SourceItem.title_redacted,
            ExtractionRun.model_name,
            ExtractionRun.prompt_version,
            ExtractionRun.extraction_confidence,
            ExtractionRun.input_tokens,
            ExtractionRun.output_tokens,
            _null(Integer),
            _null(Integer),
            _null(Integer),
            _null(Integer),
            ExtractionRun.error_message,
        )
        .join(SourceItem, SourceItem.id == ExtractionRun.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
    )
    return ingestion.union_all(extraction).subquery("runs")


def runs_query(
    *,
    kind: str | None = None,
    status: str | None = None,
    source_id: uuid.UUID | None = None,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
) -> Select:
    runs = _union()
    query = select(runs)
    if kind:
        query = query.where(runs.c.kind == kind)
    if status:
        query = query.where(runs.c.status == status)
    if source_id:
        query = query.where(runs.c.source_id == source_id)
    if started_from:
        query = query.where(runs.c.started_at >= started_from)
    if started_to:
        query = query.where(runs.c.started_at < started_to)
    return query.order_by(runs.c.started_at.desc(), runs.c.id)


def build_runs(rows: list[Any]) -> list[ProcessingRun]:
    return [ProcessingRun(**row._mapping) for row in rows]


def get_run(session: Session, run_id: uuid.UUID) -> ProcessingRunDetail | None:
    runs = _union()
    row = session.execute(select(runs).where(runs.c.id == run_id)).first()
    if row is None:
        return None
    output = None
    if row.kind == "extraction" and row.status == "succeeded":
        output = session.scalar(select(ExtractionRun.extraction_output).where(ExtractionRun.id == run_id))
    return ProcessingRunDetail(**row._mapping, output=output)
