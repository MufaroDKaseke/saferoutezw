"""Privacy-safe public response models.

These are deliberately separate from the internal schemas. They contain only text an editor
approved and published, plus general geography. No scores, AI output, evidence, reviewer
names, editorial notes or subscriber data.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import Field

from app.schemas.common import ApiModel, UtcDatetime

LocationPrecision = Literal["exact", "approximate"]


class PublicSource(ApiModel):
    name: str
    url: str | None = None


class PublicPoint(ApiModel):
    latitude: float
    longitude: float
    precision: LocationPrecision


class PublicAlertSummary(ApiModel):
    id: uuid.UUID
    headline: str
    summary: str
    location: str | None = Field(description="General location only (road and/or province).")
    province: str | None
    road_name: str | None
    hazard_type: str
    severity: str
    published_at: UtcDatetime
    updated_at: UtcDatetime
    has_map_location: bool
    sources: list[PublicSource]


class PublicAlertDetail(PublicAlertSummary):
    body: str
    point: PublicPoint | None
    notice: str


class PublicAlertPage(ApiModel):
    items: list[PublicAlertSummary]
    total: int
    page: int
    page_size: int


class PublicSummary(ApiModel):
    recent_alert_count: int
    window_days: int
    latest_alerts: list[PublicAlertSummary]
    last_updated: UtcDatetime | None


class PublicBlackspot(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    risk_level: str
    latitude: float
    longitude: float
    source_name: str
    source_reference: str | None
    observation_period_start: str | None
    observation_period_end: str | None


class PublicBlackspotList(ApiModel):
    items: list[PublicBlackspot]
    total: int
    notice: str


class PublicMapFeatureProperties(ApiModel):
    id: uuid.UUID
    title: str
    hazard_type: str
    severity: str
    status: Literal["published"]
    published_at: UtcDatetime
    location_precision: LocationPrecision
    alert_url: str


class PublicMapGeometry(ApiModel):
    type: Literal["Point"]
    coordinates: list[float]


class PublicMapFeature(ApiModel):
    type: Literal["Feature"]
    id: str
    geometry: PublicMapGeometry
    properties: PublicMapFeatureProperties


class PublicMapCollection(ApiModel):
    type: Literal["FeatureCollection"]
    features: list[PublicMapFeature]
    unlocated_count: int = Field(description="Published alerts without a reliable map position (see the list).")
    last_updated: UtcDatetime | None


# --- route planning ----------------------------------------------------------------------------


class PlaceInput(ApiModel):
    """Free text OR coordinates. Text is geocoded server-side within Zimbabwe."""

    query: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class RoutePlanRequest(ApiModel):
    origin: PlaceInput
    destination: PlaceInput
    stops: list[PlaceInput] = Field(default_factory=list, max_length=5)
    mode: Literal["drive"] = "drive"
    optimise: bool = False


class ResolvedPlace(ApiModel):
    label: str
    latitude: float
    longitude: float


class RouteHazard(ApiModel):
    alert_id: uuid.UUID
    headline: str
    hazard_type: str
    severity: str
    distance_from_route_m: float
    location_precision: LocationPrecision
    source_names: list[str]
    published_at: UtcDatetime
    updated_at: UtcDatetime
    is_closure: bool
    alert_url: str
    # Same rounding as the public map, so the route map can mark the alert where the map would.
    latitude: float
    longitude: float


class RouteBlackspot(ApiModel):
    id: uuid.UUID
    name: str
    risk_level: str
    distance_from_route_m: float
    source_name: str
    latitude: float
    longitude: float


class RoutePlanResponse(ApiModel):
    provider: str
    places: list[ResolvedPlace]
    geometry: dict[str, Any] = Field(description="GeoJSON LineString/MultiLineString from the routing engine.")
    distance_m: float
    duration_s: float
    duration_note: str
    hazards: list[RouteHazard]
    closures: list[RouteHazard]
    blackspots: list[RouteBlackspot]
    hazard_buffer_m: float
    warnings: list[str]
    disclaimer: str
    data_updated_at: UtcDatetime | None
