"""Estimate where a kilometre peg might be, as a CANDIDATE for an editor, never as a fact.

"89-kilometre peg along the Rusape-Nyanga Road" has no coordinates, and the real peg origin
(chainage zero) is not in our data. We can only say: if pegs count from Rusape, 89 km along the
driving route from Rusape to Nyanga is about here (and the mirror estimate counting from Nyanga).
Both are returned as ``ambiguous`` candidates labelled as estimates. Nothing is placed on a map
until an editor selects one, and the precision is deliberately coarse.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.core.config import Settings
from app.services.geolocation import GeocodeResult, haversine_m
from app.services.routing.base import RoutingError, RoutingProvider, RoutingUnavailable

log = logging.getLogger(__name__)

_NAME = r"[A-Z][\w'.]*(?:\s[A-Z][\w'.]*)*"
_PEG_ROAD = re.compile(
    r"(?P<km>\d+(?:\.\d+)?)\s*-?\s*(?i:km|kilomet(?:re|er)s?)\s*(?i:peg|mark(?:er)?|post)?\s*"
    rf"(?i:along|on|of|from)?\s*(?i:the)?\s*(?P<a>{_NAME})\s*(?:-|\u2013|/|(?i:\sto\s))\s*(?P<b>{_NAME})\s+(?i:road|highway|rd)\b"
)
ESTIMATE_PRECISION_M = 5_000.0  # deliberately coarse: pegs are not on our map
MAX_KM = 1_500.0


@dataclass(frozen=True)
class PegReference:
    km: float
    start: str
    end: str


def parse_peg_reference(text: str) -> PegReference | None:
    match = _PEG_ROAD.search(text or "")
    if not match:
        return None
    km = float(match.group("km"))
    if not 0 < km <= MAX_KM:
        return None
    return PegReference(km=km, start=match.group("a").strip(), end=match.group("b").strip())


def _flatten(geometry: dict) -> list[tuple[float, float]]:
    """(lat, lng) points of a LineString / MultiLineString, in order."""
    coords = geometry.get("coordinates") or []
    lines = [coords] if geometry.get("type") == "LineString" else coords
    return [(p[1], p[0]) for line in lines for p in line]


def point_along(points: list[tuple[float, float]], distance_m: float) -> tuple[float, float] | None:
    """The point ``distance_m`` along a polyline, or None if it is longer than the line."""
    travelled = 0.0
    for (lat1, lng1), (lat2, lng2) in zip(points, points[1:]):
        step = haversine_m(lat1, lng1, lat2, lng2)
        if step > 0 and travelled + step >= distance_m:
            f = (distance_m - travelled) / step
            return lat1 + (lat2 - lat1) * f, lng1 + (lng2 - lng1) * f
        travelled += step
    return None


def line_length_m(points: list[tuple[float, float]]) -> float:
    return sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(points, points[1:]))


class PegEstimator:
    source = "Estimate from Geoapify route"
    method = "peg_route_estimate"

    def __init__(self, provider: RoutingProvider) -> None:
        self._provider = provider

    def estimate(self, text: str) -> tuple[list[GeocodeResult], str] | None:
        """Candidates (counting from each end) and an explanatory note, or None if not estimable."""
        ref = parse_peg_reference(text)
        if ref is None:
            return None
        try:
            a = self._provider.geocode(ref.start)
            b = self._provider.geocode(ref.end)
            route = self._provider.route([(a.latitude, a.longitude), (b.latitude, b.longitude)], "drive")
        except (RoutingError, RoutingUnavailable) as exc:
            log.info("Peg estimate skipped: %s", type(exc).__name__)
            return None
        points = _flatten(route.geometry)
        total = line_length_m(points)
        if total <= 0 or ref.km * 1000 > total:
            return None
        results: list[GeocodeResult] = []
        for origin, distance in ((ref.start, ref.km * 1000), (ref.end, total - ref.km * 1000)):
            spot = point_along(points, distance)
            if spot is None:
                continue
            results.append(
                GeocodeResult(
                    label=f"ESTIMATE: {ref.km:g} km from {origin} along the {ref.start}-{ref.end} route",
                    latitude=spot[0],
                    longitude=spot[1],
                    precision_meters=ESTIMATE_PRECISION_M,
                    match_type="estimated_peg",
                    partial=True,
                )
            )
        if not results:
            return None
        note = (
            f"Estimate only. Pegs on the {ref.start}-{ref.end} road may not start at either town, so the "
            "real peg can be many kilometres away. Check against the report before confirming."
        )
        return results, note


def build_peg_estimator(settings: Settings) -> PegEstimator | None:
    if settings.geoapify_api_key is None or settings.routing_provider != "geoapify":
        return None
    from app.services.routing.geoapify import GeoapifyProvider

    return PegEstimator(GeoapifyProvider(settings))
