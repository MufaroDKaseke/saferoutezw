"""Turn the free-text location of an incident into a *proposed* position, honestly.

A geocoder is only a proposal source. This module never invents coordinates:

* nothing is sent for text that only gives a kilometre peg (a peg needs a verified route
  alignment and chainage origin, which we do not have), so those stay ``unresolved``;
* a result is ``resolved`` only when there is exactly one, it is not a partial match and
  its stated extent is small enough to place a marker;
* anything else is ``ambiguous``: the candidates are kept for an editor but no point is set.

Whatever is proposed here still needs an editor to confirm it (``editor_confirmed``).
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.models.enums import LocationStatus

log = logging.getLogger(__name__)

GOOGLE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
GOOGLE_SOURCE = "Google Geocoding API"
GOOGLE_METHOD = "google_geocoding"
MAX_CANDIDATES = 5
# Zimbabwe's bounding box with a small margin: catches swapped or mistyped coordinates.
ZW_LAT_RANGE = (-22.6, -15.5)
ZW_LNG_RANGE = (25.1, 33.2)

# "120km peg", "peg 85", "at the 45 km mark", "km 120"
_PEG = re.compile(
    r"(\b\d+(?:\.\d+)?\s*-?\s*(?:km|kilomet(?:re|er)s?)\s*(?:peg|mark(?:er)?|post)\b)"
    r"|(\b(?:peg|km|kilomet(?:re|er))\s*(?:peg\s*)?(?:no\.?\s*)?\d+\b)"
    r"|(\bpeg\b)",
    re.IGNORECASE,
)


class GeocoderError(Exception):
    """The provider could not answer (network, quota, credentials). Safe to retry later."""

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal  # True: the provider is unusable (bad key); stop the whole batch


@dataclass(frozen=True)
class GeocodeResult:
    label: str
    latitude: float
    longitude: float
    precision_meters: float | None  # radius of the area the provider says it matched
    match_type: str | None
    partial: bool = False


class GeocoderProvider(Protocol):
    source: str
    method: str

    def geocode(self, query: str) -> list[GeocodeResult]: ...


@dataclass
class Resolution:
    status: LocationStatus
    latitude: float | None = None
    longitude: float | None = None
    precision_meters: float | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    method: str | None = None
    source: str | None = None
    note: str | None = None


def mentions_kilometre_peg(text: str) -> bool:
    return bool(_PEG.search(text))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _precision(location_type: str | None, viewport: dict[str, Any] | None) -> float | None:
    """Radius (metres) of the area the provider claims to have matched."""
    if location_type == "ROOFTOP":
        return 30.0
    if location_type == "RANGE_INTERPOLATED":
        return 100.0
    try:
        ne, sw = viewport["northeast"], viewport["southwest"]  # type: ignore[index]
        return haversine_m(ne["lat"], ne["lng"], sw["lat"], sw["lng"]) / 2
    except (KeyError, TypeError):
        return None  # unknown extent counts as imprecise


def parse_google_results(payload: dict[str, Any]) -> list[GeocodeResult]:
    out: list[GeocodeResult] = []
    for item in payload.get("results") or []:
        try:
            geometry = item["geometry"]
            location = geometry["location"]
            out.append(
                GeocodeResult(
                    label=str(item.get("formatted_address") or "")[:300] or "Unnamed place",
                    latitude=float(location["lat"]),
                    longitude=float(location["lng"]),
                    precision_meters=_precision(geometry.get("location_type"), geometry.get("viewport")),
                    match_type=geometry.get("location_type"),
                    partial=bool(item.get("partial_match", False)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue  # skip a malformed result rather than guessing
    return out


class GoogleGeocoder:
    """Google Geocoding API, restricted to Zimbabwe. The API key is never logged."""

    source = GOOGLE_SOURCE
    method = GOOGLE_METHOD

    def __init__(self, api_key: str, *, timeout: float = 10.0, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def geocode(self, query: str) -> list[GeocodeResult]:
        try:
            response = self._client.get(
                GOOGLE_URL,
                params={"address": query, "region": "zw", "components": "country:ZW", "key": self._key},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # httpx messages can contain the request URL (and so the key): report the type only.
            raise GeocoderError(f"geocoder request failed ({type(exc).__name__})") from None
        status = payload.get("status")
        if status == "OK":
            return parse_google_results(payload)
        if status == "ZERO_RESULTS":
            return []
        if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
            raise GeocoderError(f"geocoder rejected the request ({status})", fatal=True)
        raise GeocoderError(f"geocoder unavailable ({status})")  # OVER_QUERY_LIMIT, UNKNOWN_ERROR...


def build_geocoder(settings: Settings) -> GeocoderProvider | None:
    """The configured provider, or None when geocoding is switched off or has no credentials."""
    if settings.geocoder == "google" and settings.google_maps_api_key:
        key = settings.google_maps_api_key.get_secret_value().strip()
        if key:
            return GoogleGeocoder(key, timeout=settings.geocoder_timeout_seconds)
    return None


def _candidate(result: GeocodeResult, source: str) -> dict[str, Any]:
    return {
        "label": result.label,
        "latitude": result.latitude,
        "longitude": result.longitude,
        "precision_meters": result.precision_meters,
        "match_type": result.match_type,
        "source": source,
    }


def resolve_location(text: str | None, provider: GeocoderProvider, settings: Settings) -> Resolution:
    """Propose a position for ``text``. Raises GeocoderError if the provider cannot answer."""
    cleaned = (text or "").strip()
    if not cleaned:
        return Resolution(LocationStatus.UNRESOLVED, note="The report gives no location text.")
    if mentions_kilometre_peg(cleaned):
        return Resolution(
            LocationStatus.UNRESOLVED,
            note="Kilometre pegs cannot be placed without a verified route alignment and chainage origin.",
        )

    results = provider.geocode(cleaned)
    base = {"method": provider.method, "source": provider.source}
    if not results:
        return Resolution(LocationStatus.UNRESOLVED, note="The geographic reference found no match.", **base)

    candidates = [_candidate(r, provider.source) for r in results[:MAX_CANDIDATES]]
    only = results[0] if len(results) == 1 else None
    precise = (
        only is not None
        and not only.partial
        and only.precision_meters is not None
        and only.precision_meters <= settings.geocode_max_precision_m
    )
    if only is not None and precise:
        return Resolution(
            LocationStatus.RESOLVED,
            latitude=only.latitude,
            longitude=only.longitude,
            precision_meters=only.precision_meters,
            candidates=candidates,
            note="Proposed by a geographic reference; an editor has not confirmed it.",
            **base,
        )
    reason = (
        "Several places match this description."
        if len(results) > 1
        else "The match is partial or too broad to place a marker."
    )
    return Resolution(LocationStatus.AMBIGUOUS, candidates=candidates, note=reason, **base)
