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


def region_box() -> tuple[tuple[float, float], tuple[float, float]]:
    """((lat_min, lat_max), (lng_min, lng_max)) of the monitored area: Zimbabwe unless a regional
    deployment narrows it with REGION_LAT_MIN/MAX and REGION_LNG_MIN/MAX."""
    from app.core.config import get_settings

    s = get_settings()
    return (s.region_lat_min, s.region_lat_max), (s.region_lng_min, s.region_lng_max)


def inside_region(latitude: float, longitude: float) -> bool:
    (lat_min, lat_max), (lng_min, lng_max) = region_box()
    return lat_min <= latitude <= lat_max and lng_min <= longitude <= lng_max


def geoapify_filter() -> str:
    """Geoapify's search filter: the whole of Zimbabwe, or the regional rectangle (lon/lat, west-north to east-south)."""
    box = region_box()
    if box == (ZW_LAT_RANGE, ZW_LNG_RANGE):
        return "countrycode:zw"
    (lat_min, lat_max), (lng_min, lng_max) = box
    return f"rect:{lng_min},{lat_max},{lng_max},{lat_min}"

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


GEOAPIFY_URL = "https://api.geoapify.com/v1/geocode/search"
GEOAPIFY_SOURCE = "Geoapify Geocoding API"
GEOAPIFY_METHOD = "geoapify_geocoding"
# Result types that name a single point-like place; broader types rely on the bounding box.
_GEOAPIFY_POINT_PRECISION = {"building": 30.0, "amenity": 50.0, "street": 400.0}


def parse_geoapify_results(payload: dict[str, Any]) -> list[GeocodeResult]:
    out: list[GeocodeResult] = []
    for item in payload.get("results") or []:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue  # skip a malformed result rather than guessing
        if not inside_region(lat, lon):
            continue
        rank = item.get("rank") or {}
        result_type = item.get("result_type")
        precision = _GEOAPIFY_POINT_PRECISION.get(result_type)
        bbox = item.get("bbox")
        if precision is None and isinstance(bbox, dict):
            try:
                precision = haversine_m(bbox["lat1"], bbox["lon1"], bbox["lat2"], bbox["lon2"]) / 2
            except (KeyError, TypeError):
                precision = None  # unknown extent counts as imprecise
        out.append(
            GeocodeResult(
                label=str(item.get("formatted") or "")[:300] or "Unnamed place",
                latitude=lat,
                longitude=lon,
                precision_meters=precision,
                match_type=result_type,
                partial=rank.get("match_type") not in (None, "full_match"),
            )
        )
    return out


class GeoapifyGeocoder:
    """Geoapify Geocoding API, restricted to Zimbabwe. The API key is never logged."""

    source = GEOAPIFY_SOURCE
    method = GEOAPIFY_METHOD

    def __init__(self, api_key: str, *, timeout: float = 10.0, client: httpx.Client | None = None) -> None:
        self._key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def geocode(self, query: str) -> list[GeocodeResult]:
        try:
            response = self._client.get(
                GEOAPIFY_URL,
                params={"text": query, "filter": geoapify_filter(), "limit": MAX_CANDIDATES, "format": "json", "apiKey": self._key},
            )
        except httpx.HTTPError as exc:
            # httpx messages can contain the request URL (and so the key): report the type only.
            raise GeocoderError(f"geocoder request failed ({type(exc).__name__})") from None
        if response.status_code in (401, 403):
            raise GeocoderError("geocoder rejected the API key", fatal=True)
        if response.status_code >= 400:
            raise GeocoderError(f"geocoder unavailable (HTTP {response.status_code})")
        try:
            return parse_geoapify_results(response.json())
        except ValueError:
            raise GeocoderError("geocoder returned an unreadable answer") from None


def build_geocoder(settings: Settings) -> GeocoderProvider | None:
    """The configured provider, or None when geocoding is switched off or has no credentials."""
    if settings.geocoder == "geoapify" and settings.geoapify_api_key:
        key = settings.geoapify_api_key.get_secret_value().strip()
        if key:
            return GeoapifyGeocoder(key, timeout=settings.geocoder_timeout_seconds)
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


def resolve_location(
    text: str | None, provider: GeocoderProvider, settings: Settings, peg_estimator: Any | None = None
) -> Resolution:
    """Propose a position for ``text``. Raises GeocoderError if the provider cannot answer."""
    cleaned = (text or "").strip()
    if not cleaned:
        return Resolution(LocationStatus.UNRESOLVED, note="The report gives no location text.")
    if mentions_kilometre_peg(cleaned):
        estimate = peg_estimator.estimate(cleaned) if peg_estimator is not None else None
        if estimate is not None:
            results, note = estimate
            # Never RESOLVED: an estimate has no verified chainage origin, so an editor must choose.
            return Resolution(
                LocationStatus.AMBIGUOUS,
                candidates=[_candidate(r, peg_estimator.source) for r in results],
                method=peg_estimator.method,
                source=peg_estimator.source,
                note=note,
            )
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
