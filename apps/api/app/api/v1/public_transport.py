"""Public transport information: published news, verified statistics and insights.

Strictly separate from road hazard alerts (``/public/alerts``). Only editor-approved versions
that were published as an explicit output appear here; classification scores, quality flags,
editor notes, reviewers and unreviewed candidates are never exposed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import DbSession
from app.api.errors import ERROR_RESPONSES
from app.api.pagination import Page, PageParams, page_params, paginate
from app.repositories import intelligence as repo
from app.schemas.intelligence_api import PublicStatistics, PublicTransportItem
from app.taxonomy import PrimaryCategory

router = APIRouter(prefix="/public/transport", tags=["public"], responses=ERROR_RESPONSES)

CACHE = "public, max-age=120, stale-while-revalidate=300"
PublicPage = Annotated[PageParams, Depends(page_params)]


def _cacheable(response: Response) -> None:
    response.headers["Cache-Control"] = CACHE


@router.get("/news", response_model=Page[PublicTransportItem])
def public_news(
    response: Response,
    db: DbSession,
    pagination: PublicPage,
    category: PrimaryCategory | None = None,
) -> Page[PublicTransportItem]:
    """Published transport news and public-interest reports (not hazard alerts)."""
    _cacheable(response)
    query = repo.published_base("transport_news", "analytical_report", "journalism_briefing")
    if category:
        query = query.where(repo.IntelligenceVersion.primary_category == category.value)
    rows, total = paginate(db, query, pagination)
    return Page(items=repo.build_public_items(db, rows), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/insights", response_model=Page[PublicTransportItem])
def public_insights(response: Response, db: DbSession, pagination: PublicPage) -> Page[PublicTransportItem]:
    """Published statistical insights and analytical reports."""
    _cacheable(response)
    rows, total = paginate(db, repo.published_base("statistical_insight", "analytical_report"), pagination)
    return Page(items=repo.build_public_items(db, rows), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/statistics", response_model=PublicStatistics)
def public_statistics(
    response: Response,
    db: DbSession,
    metric: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> PublicStatistics:
    """Editor-verified figures from published statistical records, each with its period and source."""
    _cacheable(response)
    return PublicStatistics(statistics=repo.public_statistics(db, metric=metric, limit=limit), note=repo.PUBLIC_STATS_NOTE)
