"""Provider-neutral types. Providers must never invent geometry: on any doubt they raise."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.services.geolocation import ZW_LAT_RANGE, ZW_LNG_RANGE


class RoutingError(Exception):
    """The request cannot be answered as asked (unknown place, no route). Client-safe message."""


class RoutingUnavailable(Exception):
    """The provider is missing, misconfigured, slow or failing. Safe to retry later."""


@dataclass(frozen=True)
class GeocodedPlace:
    label: str
    latitude: float
    longitude: float
    confidence: float | None = None  # 0..1 when the provider reports it


@dataclass(frozen=True)
class RouteResult:
    provider: str
    geometry: dict[str, Any]  # GeoJSON LineString / MultiLineString from the routing engine
    distance_m: float
    duration_s: float
    warnings: list[str] = field(default_factory=list)


class RoutingProvider(Protocol):
    name: str

    def geocode(self, query: str) -> GeocodedPlace:
        """Resolve free text to one place inside Zimbabwe, or raise RoutingError."""

    def route(self, waypoints: list[tuple[float, float]], mode: str) -> RouteResult:
        """``waypoints`` are (latitude, longitude) in visiting order (origin ... destination)."""


def inside_zimbabwe(latitude: float, longitude: float) -> bool:
    return ZW_LAT_RANGE[0] <= latitude <= ZW_LAT_RANGE[1] and ZW_LNG_RANGE[0] <= longitude <= ZW_LNG_RANGE[1]
