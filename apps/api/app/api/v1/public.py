"""Public, login-free API. Reads ONLY through ``app.repositories.public`` (published data)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import AppSettings, DbSession
from app.api.errors import ERROR_RESPONSES, ApiError, not_found
from app.api.pagination import PageParams, page_params
from app.api.rate_limit import ReadLimit, WriteLimit
from app.models.enums import IncidentType, Severity
from app.repositories import public as repo
from app.schemas.public import (
    PublicAlertDetail,
    PublicAlertPage,
    PublicBlackspotList,
    PublicMapCollection,
    PublicMapFeature,
    PublicMapFeatureProperties,
    PublicMapGeometry,
    PublicSummary,
    RoutePlanRequest,
    RoutePlanResponse,
)
from app.services.route_planning import plan_route
from app.services.routing import RoutingError, RoutingProvider, RoutingUnavailable, get_routing_provider
from app.services.zimbabwe import normalise_province

router = APIRouter(prefix="/public", tags=["public"], responses=ERROR_RESPONSES)

SUMMARY_WINDOW_DAYS = 30
CACHE = "public, max-age=60, stale-while-revalidate=120"
BLACKSPOT_NOTICE = (
    "Historical blackspots come from the cited sources and describe past risk. "
    "They are not current alerts."
)
PublicPage = Annotated[PageParams, Depends(page_params)]


def _cacheable(response: Response) -> None:
    response.headers["Cache-Control"] = CACHE


def routing_provider(settings: AppSettings) -> RoutingProvider:
    try:
        return get_routing_provider(settings)
    except RoutingUnavailable:
        raise ApiError(503, "ROUTING_UNAVAILABLE", "Route planning is not available right now.") from None


@router.get("/summary", response_model=PublicSummary, dependencies=[ReadLimit])
def get_public_summary(db: DbSession, response: Response) -> PublicSummary:
    """Recent published alerts and when public data last changed. No system-wide statistics."""
    _cacheable(response)
    count, latest, updated = repo.recent_summary(db, SUMMARY_WINDOW_DAYS, 5)
    return PublicSummary(
        recent_alert_count=count, window_days=SUMMARY_WINDOW_DAYS, latest_alerts=latest, last_updated=updated
    )


@router.get("/alerts", response_model=PublicAlertPage, dependencies=[ReadLimit])
def list_public_alerts(
    db: DbSession,
    response: Response,
    pagination: PublicPage,
    q: Annotated[str | None, Query(max_length=100)] = None,
    province: Annotated[str | None, Query(max_length=32)] = None,
    road: Annotated[str | None, Query(max_length=100)] = None,
    hazard_type: IncidentType | None = None,
) -> PublicAlertPage:
    _cacheable(response)
    canonical = None
    if province:
        canonical = normalise_province(province)
        if canonical is None:
            raise ApiError(422, "INVALID_PROVINCE", "That is not a Zimbabwe province.")
    items, total = repo.list_alerts(
        db,
        pagination,
        q=q,
        province=canonical,
        road=road,
        hazard_type=hazard_type.value if hazard_type else None,
    )
    return PublicAlertPage(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/alerts/{alert_id}", response_model=PublicAlertDetail, dependencies=[ReadLimit])
def get_public_alert(alert_id: uuid.UUID, db: DbSession, response: Response) -> PublicAlertDetail:
    _cacheable(response)
    detail = repo.get_alert(db, alert_id)
    if detail is None:
        raise not_found("ALERT_NOT_FOUND", "That alert was not found.")
    return detail


@router.get("/map", response_model=PublicMapCollection, dependencies=[ReadLimit])
def get_public_map(
    db: DbSession,
    response: Response,
    hazard_type: IncidentType | None = None,
    severity: Severity | None = None,
    since_days: Annotated[int | None, Query(ge=1, le=365)] = None,
) -> PublicMapCollection:
    """GeoJSON of published alerts that have a reliable position. Others are only counted."""
    _cacheable(response)
    since = datetime.now(UTC) - timedelta(days=since_days) if since_days else None
    rows, unlocated = repo.map_rows(
        db,
        hazard_type=hazard_type.value if hazard_type else None,
        severity=severity.value if severity else None,
        since=since,
    )
    features: list[PublicMapFeature] = []
    newest: datetime | None = None
    for alert, version, incident, lat, lng in rows:
        assert alert.published_at is not None
        newest = max(newest, alert.published_at) if newest else alert.published_at
        features.append(
            PublicMapFeature(
                type="Feature",
                id=str(alert.id),
                geometry=PublicMapGeometry(
                    type="Point",
                    coordinates=[round(lng, repo.COORD_DECIMALS), round(lat, repo.COORD_DECIMALS)],
                ),
                properties=PublicMapFeatureProperties(
                    id=alert.id,
                    title=version.headline,
                    hazard_type=incident.incident_type,
                    severity=incident.severity,
                    status="published",
                    published_at=alert.published_at,
                    location_precision=repo.precision_label(incident),
                    alert_url=f"/public/alerts/{alert.id}",
                ),
            )
        )
    return PublicMapCollection(
        type="FeatureCollection", features=features, unlocated_count=unlocated, last_updated=newest
    )


@router.get("/blackspots", response_model=PublicBlackspotList, dependencies=[ReadLimit])
def list_public_blackspots(db: DbSession, response: Response) -> PublicBlackspotList:
    _cacheable(response)
    items = repo.list_blackspots(db)
    return PublicBlackspotList(items=items, total=len(items), notice=BLACKSPOT_NOTICE)


@router.post("/routes/plan", response_model=RoutePlanResponse, dependencies=[WriteLimit])
def plan_public_route(
    body: RoutePlanRequest,
    db: DbSession,
    settings: AppSettings,
    provider: Annotated[RoutingProvider, Depends(routing_provider)],
) -> RoutePlanResponse:
    try:
        return plan_route(db, provider, settings, body)
    except RoutingError as exc:
        raise ApiError(422, "ROUTE_INPUT_INVALID", str(exc)) from None
    except RoutingUnavailable:
        raise ApiError(503, "ROUTING_UNAVAILABLE", "Route planning is not available right now.") from None
