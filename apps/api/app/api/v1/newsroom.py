"""NUST FM newsroom API: collected articles, their general-news classification and a simple review flag.

Mounted only when ``APP_MODE=nust_newsroom``. Reads are open to admin, editor, analyst and reporter (the
journalists); writes (the review flag and retrying a failed article) need admin or editor. Nothing here touches incidents,
bulletins, alerts or any road-safety approval safeguard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession, Editor, NewsroomReader
from app.api.errors import ERROR_RESPONSES, conflict, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models import SourceItem
from app.models.enums import ProcessingStatus
from app.repositories import newsroom as repo
from app.schemas.newsroom import NEWS_CATEGORY_LABELS, NewsCategory
from app.schemas.newsroom_api import (
    ArticleDetail,
    ArticleState,
    ArticleSummary,
    CategoryOut,
    NewsroomSummary,
    ReviewRequest,
    ReviewStatus,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/newsroom", tags=["newsroom"], responses=ERROR_RESPONSES)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(auth: NewsroomReader) -> list[CategoryOut]:
    return [CategoryOut(value=value, label=label) for value, label in NEWS_CATEGORY_LABELS.items()]


@router.get("/summary", response_model=NewsroomSummary)
def newsroom_summary(auth: NewsroomReader, db: DbSession, settings: AppSettings) -> NewsroomSummary:
    return repo.summary(db, settings)


@router.get("/articles", response_model=Page[ArticleSummary])
def list_articles(
    auth: NewsroomReader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200, description="Headline, excerpt, article text or AI summary contains")] = None,
    publisher_id: uuid.UUID | None = None,
    category: Annotated[NewsCategory | None, Query(description="Primary or secondary news category")] = None,
    state: Annotated[ArticleState | None, Query(description="classified, pending, failed, or skipped (kept out by an earlier road-safety screen)")] = None,
    review_status: ReviewStatus | None = None,
    published_from: datetime | None = None,
    published_to: datetime | None = None,
    collected_from: datetime | None = None,
    collected_to: datetime | None = None,
    sort: Literal["collected_at", "published_at"] = "collected_at",
    order: Literal["asc", "desc"] = "desc",
) -> Page[ArticleSummary]:
    filters = repo.ArticleFilters(
        q=q,
        source_id=publisher_id,
        category=category.value if category else None,
        state=state,
        review_status=review_status,
        published_from=published_from,
        published_to=published_to,
        collected_from=collected_from,
        collected_to=collected_to,
        sort=sort,
        descending=order == "desc",
    )
    rows, total = paginate(db, repo.articles_query(filters), pagination)
    return Page(items=repo.build_summaries(rows), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/articles/{article_id}", response_model=ArticleDetail)
def get_article(article_id: uuid.UUID, auth: NewsroomReader, db: DbSession) -> ArticleDetail:
    detail = repo.get_detail(db, article_id)
    if detail is None:
        raise not_found("ARTICLE_NOT_FOUND", "No such article.")
    return detail


@router.patch("/articles/{article_id}/review", response_model=ArticleDetail)
def set_review(article_id: uuid.UUID, body: ReviewRequest, auth: Editor, db: DbSession) -> ArticleDetail:
    """Mark an article New / Reviewed / Used / Dismissed. A flag for the newsroom, recorded in the audit trail."""
    item = db.get(SourceItem, article_id)
    if item is None:
        raise not_found("ARTICLE_NOT_FOUND", "No such article.")
    previous = (item.source_metadata or {}).get("newsroom_review", {}).get("status", "new")
    item.source_metadata = {
        **item.source_metadata,
        "newsroom_review": {
            "status": body.status,
            "by": auth.user.display_name,
            "by_id": str(auth.user.id),
            "at": datetime.now(UTC).isoformat(),
            "note": (body.note or "").strip() or None,
        },
    }
    record_audit(
        db,
        actor_id=auth.user.id,
        action="newsroom.article_reviewed",
        entity_type="source_item",
        entity_id=item.id,
        details={"status": body.status, "previous": previous},
    )
    db.commit()
    detail = repo.get_detail(db, article_id)
    assert detail is not None
    return detail


@router.post("/articles/{article_id}/retry", response_model=ArticleDetail)
def retry_article(article_id: uuid.UUID, auth: Editor, db: DbSession) -> ArticleDetail:
    """Queue a failed article again. The original article and its failure history are kept."""
    item = db.get(SourceItem, article_id)
    if item is None:
        raise not_found("ARTICLE_NOT_FOUND", "No such article.")
    if repo.article_state(item) != "failed":
        raise conflict("NOT_FAILED", "Only failed articles can be retried.")
    meta = {k: v for k, v in item.source_metadata.items() if k != "fetch_attempts"}
    meta["extraction_retry_epoch"] = datetime.now(UTC).isoformat()  # earlier failed runs no longer count against it
    item.source_metadata = meta
    if item.processing_status == ProcessingStatus.FETCH_FAILED.value:
        item.processing_status = ProcessingStatus.SCREENED.value
        item.fetch_status = None
        item.fetch_error = None
    else:
        item.processing_status = ProcessingStatus.FETCHED.value
    record_audit(
        db,
        actor_id=auth.user.id,
        action="newsroom.article_retry",
        entity_type="source_item",
        entity_id=item.id,
        details={},
    )
    db.commit()
    detail = repo.get_detail(db, article_id)
    assert detail is not None
    return detail
