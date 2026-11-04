"""Geoapify geocoding + routing (OpenStreetMap based). Requires GEOAPIFY_API_KEY.

The API key travels in the query string, so httpx request logging is silenced to WARNING to
keep it out of logs. No traffic data is requested: durations are engine estimates only.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.services.routing.base import (
    GeocodedPlace,
    RouteResult,
    RoutingError,
    RoutingUnavailable,
    inside_zimbabwe,
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
ROUTING_URL = "https://api.geoapify.com/v1/routing"
MODES = {"drive": "drive"}


class GeoapifyProvider:
    name = "geoapify"

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        if settings.geoapify_api_key is None:
            raise RoutingUnavailable("Route planning is not configured.")
        self._key = settings.geoapify_api_key.get_secret_value()
        self._timeout = settings.routing_timeout_seconds
        self._client = client or httpx.Client(timeout=self._timeout)

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.get(url, params={**params, "apiKey": self._key})
        except httpx.TimeoutException:
            raise RoutingUnavailable("The routing service timed out.") from None
        except httpx.HTTPError:
            raise RoutingUnavailable("The routing service could not be reached.") from None
        if response.status_code in (401, 403):
            log.error("Geoapify rejected the API key (HTTP %s)", response.status_code)
            raise RoutingUnavailable("Route planning is not available.")
        if response.status_code == 429:
            raise RoutingUnavailable("The routing service is busy. Try again shortly.")
        if response.status_code == 400:
            raise RoutingError("The routing service could not use those locations.")
        if response.status_code >= 400:
            raise RoutingUnavailable("The routing service returned an error.")
        try:
            return response.json()
        except ValueError:
            raise RoutingUnavailable("The routing service returned an unreadable answer.") from None

    def geocode(self, query: str) -> GeocodedPlace:
        data = self._get(
            GEOCODE_URL,
            {"text": query, "filter": "countrycode:zw", "limit": 5, "format": "json", "lang": "en"},
        )
        for result in data.get("results") or []:
            lat, lon = result.get("lat"), result.get("lon")
            if lat is None or lon is None or not inside_zimbabwe(lat, lon):
                continue
            rank = result.get("rank") or {}
            return GeocodedPlace(
                label=str(result.get("formatted") or query)[:200],
                latitude=float(lat),
                longitude=float(lon),
                confidence=rank.get("confidence"),
            )
        raise RoutingError(f"Could not find '{query[:60]}' in Zimbabwe.")

    def route(self, waypoints: list[tuple[float, float]], mode: str) -> RouteResult:
        if mode not in MODES:
            raise RoutingError("That travel mode is not supported.")
        if len(waypoints) < 2:
            raise RoutingError("A route needs at least an origin and a destination.")
        joined = "|".join(f"{lat},{lon}" for lat, lon in waypoints)
        data = self._get(ROUTING_URL, {"waypoints": joined, "mode": MODES[mode]})
        features = data.get("features") or []
        if not features:
            raise RoutingError("No driving route was found between those places.")
        feature = features[0]
        geometry = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        if geometry.get("type") not in {"LineString", "MultiLineString"} or not geometry.get("coordinates"):
            raise RoutingError("No driving route was found between those places.")
        try:
            distance, duration = float(props["distance"]), float(props["time"])
        except (KeyError, TypeError, ValueError):
            raise RoutingUnavailable("The routing service returned an incomplete route.") from None
        return RouteResult(provider=self.name, geometry=geometry, distance_m=distance, duration_s=duration)
