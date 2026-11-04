"""MOCK routing provider for development and tests only. Never used unless selected explicitly.

Its "route" is a straight line between the waypoints, which is NOT a road route; the
provider name ``mock`` is returned so every response says so.
"""

from __future__ import annotations

import math

from app.services.routing.base import (
    GeocodedPlace,
    RouteResult,
    RoutingError,
    RoutingUnavailable,
    inside_zimbabwe,
)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


class MockRoutingProvider:
    name = "mock"

    def __init__(self, places: dict[str, tuple[float, float]] | None = None, *, fail: str | None = None) -> None:
        self.places = {k.lower(): v for k, v in (places or {}).items()}
        self.fail = fail  # "unavailable" -> RoutingUnavailable on every call
        self.calls: list[list[tuple[float, float]]] = []

    def geocode(self, query: str) -> GeocodedPlace:
        if self.fail == "unavailable":
            raise RoutingUnavailable("The routing service timed out.")
        found = self.places.get(query.strip().lower())
        if found is None or not inside_zimbabwe(*found):
            raise RoutingError(f"Could not find '{query[:60]}' in Zimbabwe.")
        return GeocodedPlace(label=query.strip(), latitude=found[0], longitude=found[1], confidence=1.0)

    def route(self, waypoints: list[tuple[float, float]], mode: str) -> RouteResult:
        if self.fail == "unavailable":
            raise RoutingUnavailable("The routing service timed out.")
        if len(waypoints) < 2:
            raise RoutingError("A route needs at least an origin and a destination.")
        self.calls.append(list(waypoints))
        coords = [[lon, lat] for lat, lon in waypoints]
        distance = sum(haversine_m(waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1))
        return RouteResult(
            provider=self.name,
            geometry={"type": "LineString", "coordinates": coords},
            distance_m=distance,
            duration_s=distance / 16.7,  # ~60 km/h; placeholder only
            warnings=["MOCK route: a straight line, not a road route."],
        )
