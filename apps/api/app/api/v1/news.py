"""News monitor: ingested articles with their screening, fetch and extraction state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Reader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models.enums import ProcessingStatus
from app.repositories import news as repo
from app.schemas.news import NewsItemDetail, NewsItemSummary

router = APIRouter(prefix="/news", tags=["news"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[NewsItemSummary])
def list_news(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200, description="Headline contains")] = None,
    source_id: uuid.UUID | None = None,
    processing_status: ProcessingStatus | None = None,
    relevant: Annotated[bool | None, Query(description="Passed (true) / failed (false) the keyword screen")] = None,
    has_incident: bool | None = None,
    received_from: datetime | None = None,
    received_to: datetime | None = None,
    sort: Literal["received_at", "published_at"] = "received_at",
    order: Literal["asc", "desc"] = "desc",
) -> Page[NewsItemSummary]:
    filters = repo.NewsFilters(
        q=q,
        source_id=source_id,
        processing_status=processing_status.value if processing_status else None,
        relevant=relevant,
        has_incident=has_incident,
        received_from=received_from,
        received_to=received_to,
        sort=sort,
        descending=order == "desc",
    )
    rows, total = paginate(db, repo.news_list_query(filters), pagination)
    return Page(
        items=repo.build_summaries(db, rows),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{item_id}", response_model=NewsItemDetail)
def get_news_item(item_id: uuid.UUID, auth: Reader, db: DbSession) -> NewsItemDetail:
    row = repo.get_item_row(db, item_id)
    if row is None:
        raise not_found("NEWS_ITEM_NOT_FOUND", "The requested article was not found.")
    return repo.build_detail(db, row)
