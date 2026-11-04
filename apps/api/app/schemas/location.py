"""Location resolution as exposed to clients.

``coordinates`` is present only for ``resolved`` and ``editor_confirmed`` locations.
Ambiguous results expose their candidates but never a point.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import Field

from app.models import Incident
from app.models.enums import LocationStatus
from app.schemas.common import ApiModel, UtcDatetime


class Coordinates(ApiModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class LocationCandidate(ApiModel):
    label: str
    latitude: float
    longitude: float
    precision_meters: float | None = None
    match_type: str | None = None
    source: str


class LocationOut(ApiModel):
    status: LocationStatus
    raw_location: str | None
    coordinates: Coordinates | None
    candidates: list[LocationCandidate]
    resolution_method: str | None
    source: str | None
    precision_meters: float | None
    confirmed_by_editor: bool
    confirmed_by: uuid.UUID | None = None
    confirmed_at: UtcDatetime | None
    updated_at: UtcDatetime | None
    note: str | None


def _candidates(raw: Any) -> list[LocationCandidate]:
    out: list[LocationCandidate] = []
    for item in raw or []:
        try:
            out.append(LocationCandidate.model_validate(item))
        except ValueError:
            continue  # a malformed stored candidate must not break the incident page
    return out


def build_location(incident: Incident, lat: float | None, lng: float | None) -> LocationOut:
    shown = incident.location_status in (LocationStatus.RESOLVED, LocationStatus.EDITOR_CONFIRMED)
    return LocationOut(
        status=LocationStatus(incident.location_status),
        raw_location=incident.location_text,
        coordinates=Coordinates(latitude=lat, longitude=lng) if shown and lat is not None and lng is not None else None,
        candidates=_candidates(incident.location_candidates),
        resolution_method=incident.location_method,
        source=incident.location_source,
        precision_meters=incident.location_precision_m,
        confirmed_by_editor=incident.location_status == LocationStatus.EDITOR_CONFIRMED,
        confirmed_by=incident.location_confirmed_by,
        confirmed_at=incident.location_confirmed_at,
        updated_at=incident.location_updated_at,
        note=incident.location_note,
    )
