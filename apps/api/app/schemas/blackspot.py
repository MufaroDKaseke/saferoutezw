"""Blackspot, match and map responses (GeoJSON coordinates are [longitude, latitude])."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from app.models.enums import IncidentStatus, IncidentType, LocationStatus, RiskLevel, Severity
from app.schemas.common import ApiModel, UtcDatetime


class GeoJsonPoint(ApiModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class BlackspotOut(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    risk_level: RiskLevel
    source_name: str
    source_reference: str | None
    observation_period_start: date | None
    observation_period_end: date | None
    latitude: float
    longitude: float
    geometry: GeoJsonPoint
    nearby_incident_count: int = 0


class BlackspotMatchOut(ApiModel):
    blackspot: BlackspotOut
    distance_meters: float


MatchStatus = Literal["unavailable", "location_unknown", "no_match", "matched"]


class BlackspotMatchesOut(ApiModel):
    """``unavailable``: no sourced blackspot data exists. ``location_unknown``: the incident has
    no firm position. ``no_match``: located, nothing recorded within the radius (not proof of safety)."""

    status: MatchStatus
    radius_meters: float
    geographic_risk_score: float | None
    matches: list[BlackspotMatchOut]


MarkerKind = Literal["candidate", "editor_confirmed", "approved"]


class MapIncident(ApiModel):
    id: uuid.UUID
    reference_code: str
    incident_type: IncidentType
    severity: Severity
    status: IncidentStatus
    marker_kind: MarkerKind
    location_status: LocationStatus
    label: str | None
    latitude: float
    longitude: float
    precision_meters: float | None
    occurred_at: UtcDatetime | None


class MapData(ApiModel):
    incidents: list[MapIncident]
    blackspots: list[BlackspotOut]
    unmapped_incident_count: int
    generated_at: UtcDatetime
