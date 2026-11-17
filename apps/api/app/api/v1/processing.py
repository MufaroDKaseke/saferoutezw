"""Processing history: ingestion and AI extraction runs. Prompts and article text are never exposed."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter

from app.api.deps import DbSession, OperationsReader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.repositories import processing as repo
from app.schemas.processing import ProcessingBacklog, ProcessingRun, ProcessingRunDetail, RunKind

router = APIRouter(prefix="/processing", tags=["processing"], responses=ERROR_RESPONSES)


@router.get("/backlog", response_model=ProcessingBacklog)
def processing_backlog(auth: OperationsReader, db: DbSession) -> ProcessingBacklog:
    return repo.backlog(db)


@router.get("/runs", response_model=Page[ProcessingRun])
def list_processing_runs(
    auth: OperationsReader,
    db: DbSession,
    pagination: Pagination,
    kind: RunKind | None = None,
    status: str | None = None,
    source_id: uuid.UUID | None = None,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
) -> Page[ProcessingRun]:
    query = repo.runs_query(
        kind=kind, status=status, source_id=source_id, started_from=started_from, started_to=started_to
    )
    rows, total = paginate(db, query, pagination)
    return Page(
        items=repo.build_runs(rows),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/runs/{run_id}", response_model=ProcessingRunDetail)
def get_processing_run(run_id: uuid.UUID, auth: OperationsReader, db: DbSession) -> ProcessingRunDetail:
    run = repo.get_run(db, run_id)
    if run is None:
        raise not_found("RUN_NOT_FOUND", "The requested run was not found.")
    return run
