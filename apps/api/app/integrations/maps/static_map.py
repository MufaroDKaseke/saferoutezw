"""Static map images (Geoapify Static Maps) for WhatsApp alerts and route checks.

A map is a nice-to-have on top of a message that already says everything in words, so every
failure here (no key, timeout, bad answer) returns ``None`` and the caller sends the text alone.
The API key is never logged. Only coordinates the public map would already show are passed in.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import Settings

log = logging.getLogger(__name__)

STATIC_MAP_URL = "https://maps.geoapify.com/v1/staticmap"
WIDTH, HEIGHT = 800, 500
MAX_ROUTE_POINTS = 150  # keeps the request URL short; plenty for a line drawn at 800 px
MAX_MARKERS = 10
MAX_IMAGE_BYTES = 4_500_000  # WhatsApp accepts images up to 5 MB

HAZARD_COLOR = "#dc2626"
CLOSURE_COLOR = "#7f1d1d"
ORIGIN_COLOR = "#16a34a"
DESTINATION_COLOR = "#1d4ed8"
ROUTE_COLOR = "#0ea5e9"

Point = tuple[float, float]  # (latitude, longitude)


def _key(settings: Settings) -> str | None:
    if settings.geoapify_api_key is None:
        return None
    key = settings.geoapify_api_key.get_secret_value().strip()
    return key or None


def _marker(lat: float, lon: float, color: str, kind: str = "awesome", size: str = "large") -> str:
    return f"lonlat:{lon:.5f},{lat:.5f};type:{kind};color:{quote(color, safe='')};size:{size}"


def _line_points(geometry: dict[str, Any]) -> list[Point]:
    """(lat, lon) points of a GeoJSON LineString / MultiLineString, thinned to MAX_ROUTE_POINTS."""
    kind, coords = geometry.get("type"), geometry.get("coordinates") or []
    parts = [coords] if kind == "LineString" else coords if kind == "MultiLineString" else []
    points: list[Point] = []
    for part in parts:
        for c in part:
            if len(c) >= 2:
                points.append((float(c[1]), float(c[0])))
    if len(points) > MAX_ROUTE_POINTS:
        step = (len(points) - 1) / (MAX_ROUTE_POINTS - 1)
        points = [points[round(i * step)] for i in range(MAX_ROUTE_POINTS)]
    return points


def _fetch(settings: Settings, params: str) -> bytes | None:
    key = _key(settings)
    if key is None:
        return None
    try:
        response = httpx.get(
            f"{STATIC_MAP_URL}?{params}&apiKey={quote(key, safe='')}",
            timeout=min(settings.whatsapp_api_timeout_seconds, 10),
        )
    except httpx.HTTPError as error:
        log.warning("static map request failed (%s)", type(error).__name__)  # never the URL: it holds the key
        return None
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not content_type.startswith("image/") or len(response.content) > MAX_IMAGE_BYTES:
        log.warning("static map not usable (http=%s)", response.status_code)
        return None
    return response.content


def incident_map(settings: Settings, latitude: float, longitude: float, *, zoom: int = 13) -> bytes | None:
    """One red pin on a street map, centred on the incident."""
    params = (
        f"style=osm-bright&width={WIDTH}&height={HEIGHT}&center=lonlat:{longitude:.5f},{latitude:.5f}&zoom={zoom}"
        f"&marker={_marker(latitude, longitude, HAZARD_COLOR)}"
    )
    return _fetch(settings, params)


def route_map(
    settings: Settings,
    geometry: dict[str, Any],
    origin: Point,
    destination: Point,
    hazards: Sequence[tuple[float, float, bool]] = (),
) -> bytes | None:
    """The route line, start (green), end (blue) and alert markers (red; dark red for closures).

    ``hazards`` holds (latitude, longitude, is_closure). The map zooms to fit everything.
    """
    markers = [_marker(*origin, ORIGIN_COLOR, "material", "medium"), _marker(*destination, DESTINATION_COLOR, "material", "medium")]
    markers += [_marker(lat, lon, CLOSURE_COLOR if closed else HAZARD_COLOR) for lat, lon, closed in _limit(hazards)]
    params = f"style=osm-bright&width={WIDTH}&height={HEIGHT}"
    line = _line_points(geometry)
    if len(line) >= 2:
        coords = ",".join(f"{lon:.5f},{lat:.5f}" for lat, lon in line)
        params += f"&geometry=polyline:{coords};linewidth:5;linecolor:{quote(ROUTE_COLOR, safe='')}"
    params += "&marker=" + "|".join(markers)
    return _fetch(settings, params)


def _limit(items: Iterable[tuple[float, float, bool]]) -> list[tuple[float, float, bool]]:
    return list(items)[:MAX_MARKERS]
