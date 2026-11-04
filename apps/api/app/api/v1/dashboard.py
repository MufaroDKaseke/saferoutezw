"""Dashboard summary and activity."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Reader
from app.api.errors import ERROR_RESPONSES
from app.repositories import dashboard as repo
from app.schemas.dashboard import DashboardActivity, DashboardSummary, MonthlyIncidents, Range

router = APIRouter(prefix="/dashboard", tags=["dashboard"], responses=ERROR_RESPONSES)

RangeParam = Annotated[Range, Query(description="Time window ending now (UTC).")]


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(auth: Reader, db: DbSession, range: RangeParam = "24h") -> DashboardSummary:
    return repo.summary(db, range)


@router.get("/activity", response_model=DashboardActivity)
def dashboard_activity(auth: Reader, db: DbSession, range: RangeParam = "24h") -> DashboardActivity:
    return repo.activity(db, range)


@router.get("/incidents-by-month", response_model=MonthlyIncidents)
def dashboard_incidents_by_month(
    auth: Reader,
    db: DbSession,
    months: Annotated[int, Query(ge=1, le=24, description="How many calendar months to show, ending this month.")] = 6,
) -> MonthlyIncidents:
    """Road incidents per month (Zimbabwe time) by severity. Rejected reports are excluded."""
    return repo.incidents_by_month(db, months)
