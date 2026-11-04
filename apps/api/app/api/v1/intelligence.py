"""Transport intelligence: classified records, statistics and the editors' review workflow.

Readers (admin, editor, analyst) can browse; only editors/admins can change or publish.
Keep literal paths (categories, statistics, ...) above ``/{record_id}``.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, Editor, Reader
from app.api.errors import ERROR_RESPONSES, ApiError, not_found
from app.api.pagination import Page, Pagination, paginate
from app.repositories import intelligence as repo
from app.schemas.intelligence_api import (
    CategoriesOut,
    InsightsOut,
    IntelligenceDetail,
    IntelligenceReviewCreate,
    IntelligenceSummary,
    OutputOut,
    OverviewOut,
    PublishOutputRequest,
    StatisticsOut,
    TrendsOut,
    VersionCreate,
    VersionOut,
)
from app.models.intelligence import IntelligenceVersion
from app.services import intelligence_editorial as editorial
from app.taxonomy import PrimaryCategory, RecordKind, RecordStatus

router = APIRouter(prefix="/intelligence", tags=["intelligence"], responses=ERROR_RESPONSES)


@router.get("", response_model=Page[IntelligenceSummary])
def list_intelligence(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    category: PrimaryCategory | None = None,
    subtype: Annotated[str | None, Query(max_length=40)] = None,
    record_kind: RecordKind | None = None,
    status_: Annotated[RecordStatus | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    province: Annotated[str | None, Query(max_length=60, description="Province or region contains")] = None,
    source_id: uuid.UUID | None = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    q: Annotated[str | None, Query(max_length=200, description="Headline or summary contains")] = None,
    has_incident: bool | None = None,
    topic_key: Annotated[str | None, Query(max_length=200)] = None,
) -> Page[IntelligenceSummary]:
    filters = repo.IntelligenceFilters(
        category=category.value if category else None, subtype=subtype,
        record_kind=record_kind.value if record_kind else None,
        status=status_.value if status_ else None, date_from=date_from, date_to=date_to,
        province=province, source_id=source_id, min_confidence=min_confidence, q=q,
        has_incident=has_incident, topic_key=topic_key,
    )
    rows, total = paginate(db, repo.list_query(filters), pagination)
    return Page(items=repo.build_summaries(db, rows), total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/categories", response_model=CategoriesOut)
def get_categories(auth: Reader, db: DbSession) -> CategoriesOut:
    """The central taxonomy with per-category counts."""
    return repo.categories(db)


@router.get("/overview", response_model=OverviewOut)
def get_overview(auth: Reader, db: DbSession) -> OverviewOut:
    return repo.overview(db)


@router.get("/statistics", response_model=StatisticsOut)
def get_statistics(
    auth: Reader,
    db: DbSession,
    metric: Annotated[str | None, Query(max_length=120)] = None,
    source: Annotated[str | None, Query(max_length=120)] = None,
    verified_only: bool = False,
    period_from: date | None = None,
    period_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> StatisticsOut:
    """Reported figures grouped per metric/unit/coverage. Periods and sources are never merged."""
    return repo.statistics(
        db, metric=metric, source=source, verified_only=verified_only,
        period_from=period_from, period_to=period_to, limit=limit,
    )


@router.get("/trends", response_model=TrendsOut)
def get_trends(
    auth: Reader,
    db: DbSession,
    months: Annotated[int, Query(ge=1, le=24)] = 12,
    category: PrimaryCategory | None = None,
) -> TrendsOut:
    return repo.trends(db, months=months, category=category.value if category else None)


@router.get("/insights", response_model=InsightsOut)
def get_insights(auth: Reader, db: DbSession) -> InsightsOut:
    """Leads for editors: related coverage, corridor concentrations, newly reported statistics."""
    return repo.insights(db)


@router.get("/{record_id}", response_model=IntelligenceDetail)
def get_intelligence(record_id: uuid.UUID, auth: Reader, db: DbSession) -> IntelligenceDetail:
    row = repo.get_row(db, record_id)
    if row is None:
        raise not_found("INTELLIGENCE_NOT_FOUND", "The requested record was not found.")
    return repo.build_detail(db, row)


@router.post("/{record_id}/versions", response_model=VersionOut, status_code=status.HTTP_201_CREATED)
def create_intelligence_version(record_id: uuid.UUID, body: VersionCreate, auth: Editor, db: DbSession) -> VersionOut:
    """Save a new immutable editorial version: corrected classification, summary, scope, date, figures."""
    version = editorial.save_version(db, auth.user, record_id, body)
    return VersionOut(
        id=version.id, version_number=version.version_number, headline=version.headline,
        summary=version.summary, primary_category=version.primary_category,
        primary_subtype=version.primary_subtype, geographic_scope=version.geographic_scope,
        event_date=version.event_date, figures=version.figures, source_attribution=version.source_attribution,
        change_note=version.change_note, created_by_name=auth.user.display_name,
        created_at=version.created_at, is_latest=True,
    )


@router.post("/{record_id}/reviews", response_model=IntelligenceDetail, status_code=status.HTTP_201_CREATED)
def create_intelligence_review(record_id: uuid.UUID, body: IntelligenceReviewCreate, auth: Editor, db: DbSession) -> IntelligenceDetail:
    """Approve, reject or request changes on the latest version. The reviewer is the signed-in user."""
    if body.decision != "approved" and not (body.notes or "").strip():
        raise ApiError(422, "NOTES_REQUIRED", "Notes are required to reject or request changes.")
    editorial.record_review(db, auth.user, record_id, body.decision, body.version_id, body.notes)
    return repo.build_detail(db, repo.get_row(db, record_id))


@router.post("/{record_id}/publish", response_model=IntelligenceDetail, status_code=status.HTTP_201_CREATED)
def publish_intelligence_output(record_id: uuid.UUID, body: PublishOutputRequest, auth: Editor, db: DbSession) -> IntelligenceDetail:
    """Publish the approved latest version as one chosen output. Never a hazard alert."""
    editorial.publish_output(db, auth.user, record_id, body.output_type)
    return repo.build_detail(db, repo.get_row(db, record_id))


@router.post("/outputs/{output_id}/withdraw", response_model=OutputOut)
def withdraw_intelligence_output(output_id: uuid.UUID, auth: Editor, db: DbSession) -> OutputOut:
    output = editorial.withdraw_output(db, auth.user, output_id)
    number = db.scalar(
        select(IntelligenceVersion.version_number).where(IntelligenceVersion.id == output.version_id)
    )
    return OutputOut(id=output.id, output_type=output.output_type, status=output.status,
                     version_number=number or 0, published_at=output.published_at, withdrawn_at=output.withdrawn_at)

