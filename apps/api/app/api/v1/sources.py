"""Data sources and their ingestion history (read-only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Reader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models import Source
from app.models.enums import IngestionStatus, SourceKind
from app.repositories import sources as repo
from app.schemas.source import IngestionRunOut, SourceOut

router = APIRouter(prefix="/sources", tags=["sources"], responses=ERROR_RESPONSES)


def _source_or_404(db, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise not_found("SOURCE_NOT_FOUND", "The requested source was not found.")
    return source


@router.get("", response_model=Page[SourceOut])
def list_sources(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200)] = None,
    kind: SourceKind | None = None,
    enabled: bool | None = None,
) -> Page[SourceOut]:
    query = repo.source_list_query(q=q, kind=kind.value if kind else None, enabled=enabled)
    rows, total = paginate(db, query, pagination)
    return Page(
        items=repo.build_sources(db, [r[0] for r in rows]),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{source_id}", response_model=SourceOut)
def get_source(source_id: uuid.UUID, auth: Reader, db: DbSession) -> SourceOut:
    return repo.build_sources(db, [_source_or_404(db, source_id)])[0]


@router.get("/{source_id}/runs", response_model=Page[IngestionRunOut])
def list_source_runs(
    source_id: uuid.UUID,
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    status: IngestionStatus | None = None,
) -> Page[IngestionRunOut]:
    _source_or_404(db, source_id)
    query = repo.runs_query(source_id=source_id, status=status.value if status else None)
    rows, total = paginate(db, query, pagination)
    return Page(
        items=repo.build_runs(rows),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )
