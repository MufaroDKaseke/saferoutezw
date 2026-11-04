"""Blackspot, match and map queries (PostGIS geography, GiST indexed)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Select, cast, func, select
from sqlalchemy.orm import Session

from app.models import Blackspot, Incident, IncidentBlackspotMatch
from app.models.enums import IncidentStatus, LocationStatus
from app.repositories.incidents import _like
from app.schemas.blackspot import (
    BlackspotMatchesOut,
    BlackspotMatchOut,
    BlackspotOut,
    GeoJsonPoint,
    MapData,
    MapIncident,
)
from app.services.blackspot_matching import match_status

B_LAT = func.ST_Y(cast(Blackspot.geom, Geometry)).label("lat")
B_LNG = func.ST_X(cast(Blackspot.geom, Geometry)).label("lng")
I_LAT = func.ST_Y(cast(Incident.geom, Geometry)).label("lat")
I_LNG = func.ST_X(cast(Incident.geom, Geometry)).label("lng")

MAP_LIMIT = 1000
LOCATED = (LocationStatus.RESOLVED.value, LocationStatus.EDITOR_CONFIRMED.value)
OPEN = (IncidentStatus.CANDIDATE.value, IncidentStatus.UNDER_REVIEW.value)
HIDDEN_ON_MAP = (IncidentStatus.REJECTED.value, IncidentStatus.ARCHIVED.value)


def blackspot_list_query(*, q: str | None = None, risk_level: str | None = None) -> Select:
    query = select(Blackspot, B_LAT, B_LNG)
    if q:
        query = query.where(Blackspot.name.ilike(_like(q.strip())))
    if risk_level:
        query = query.where(Blackspot.risk_level == risk_level)
    return query.order_by(Blackspot.name, Blackspot.id)


def get_blackspot_row(session: Session, blackspot_id: uuid.UUID) -> Any | None:
    return session.execute(select(Blackspot, B_LAT, B_LNG).where(Blackspot.id == blackspot_id)).first()


def nearby_counts(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """How many located incidents are matched to each blackspot (one grouped query)."""
    if not ids:
        return {}
    return dict(
        session.execute(
            select(IncidentBlackspotMatch.blackspot_id, func.count())
            .where(IncidentBlackspotMatch.blackspot_id.in_(ids))
            .group_by(IncidentBlackspotMatch.blackspot_id)
        ).all()
    )


def to_blackspot(row: Any, counts: dict[uuid.UUID, int] | None = None) -> BlackspotOut:
    spot, lat, lng = row[0], row[1], row[2]
    return BlackspotOut(
        nearby_incident_count=(counts or {}).get(spot.id, 0),
        id=spot.id,
        name=spot.name,
        description=spot.description,
        risk_level=spot.risk_level,
        source_name=spot.source_name,
        source_reference=spot.source_reference,
        observation_period_start=spot.observation_period_start,
        observation_period_end=spot.observation_period_end,
        latitude=lat,
        longitude=lng,
        geometry=GeoJsonPoint(coordinates=(lng, lat)),
    )


def build_matches(session: Session, incident: Incident, radius_m: float) -> BlackspotMatchesOut:
    rows = session.execute(
        select(Blackspot, B_LAT, B_LNG, IncidentBlackspotMatch.distance_meters)
        .join(IncidentBlackspotMatch, IncidentBlackspotMatch.blackspot_id == Blackspot.id)
        .where(IncidentBlackspotMatch.incident_id == incident.id)
        .order_by(IncidentBlackspotMatch.distance_meters, Blackspot.id)
    ).all()
    return BlackspotMatchesOut(
        status=match_status(session, incident, radius_m),
        radius_meters=radius_m,
        geographic_risk_score=incident.geographic_risk_score,
        matches=[BlackspotMatchOut(blackspot=to_blackspot(r), distance_meters=r[3]) for r in rows],
    )


def _marker_kind(incident: Incident) -> str:
    if incident.status in (IncidentStatus.APPROVED, IncidentStatus.PUBLISHED):
        return "approved"
    if incident.location_status == LocationStatus.EDITOR_CONFIRMED:
        return "editor_confirmed"
    return "candidate"


def build_map(session: Session, include_blackspots: bool = True) -> MapData:
    """Only firm positions get a marker; vague or unresolved ones are counted, never drawn."""
    rows = session.execute(
        select(Incident, I_LAT, I_LNG)
        .where(
            Incident.geom.is_not(None),
            Incident.location_status.in_(LOCATED),
            Incident.status.not_in(HIDDEN_ON_MAP),
        )
        .order_by(Incident.created_at.desc(), Incident.id)
        .limit(MAP_LIMIT)
    ).all()
    unmapped = session.scalar(
        select(func.count()).where(
            Incident.status.in_(OPEN),
            Incident.location_status.not_in(LOCATED),
        )
    )
    spot_rows = session.execute(blackspot_list_query().limit(MAP_LIMIT)).all() if include_blackspots else []
    counts = nearby_counts(session, [r[0].id for r in spot_rows])
    spots = [to_blackspot(r, counts) for r in spot_rows]
    return MapData(
        incidents=[
            MapIncident(
                id=i.id,
                reference_code=i.reference_code,
                incident_type=i.incident_type,
                severity=i.severity,
                status=i.status,
                marker_kind=_marker_kind(i),
                location_status=i.location_status,
                label=i.location_text,
                latitude=lat,
                longitude=lng,
                precision_meters=i.location_precision_m,
                occurred_at=i.occurred_at,
            )
            for i, lat, lng in rows
        ],
        blackspots=spots,
        unmapped_incident_count=unmapped or 0,
        generated_at=datetime.now(UTC),
    )
