"""Match located incidents against sourced historical blackspots with PostGIS."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, exists, func, select
from sqlalchemy.orm import Session

from app.models import Blackspot, Incident, IncidentBlackspotMatch
from app.models.enums import LocationStatus
from app.services.scoring import geographic_risk, raise_priority


def blackspots_exist(session: Session) -> bool:
    return bool(session.scalar(select(exists().where(Blackspot.id.is_not(None)))))


def eligible_for_matching(incident: Incident, radius_m: float) -> bool:
    """Only positions that are firm enough for the search radius may be matched.

    ``resolved`` needs a known precision within the radius; ``editor_confirmed`` is a human
    assertion, so it is accepted unless the editor recorded a coarser precision.
    """
    if incident.geom is None:
        return False
    if incident.location_status == LocationStatus.EDITOR_CONFIRMED:
        return incident.location_precision_m is None or incident.location_precision_m <= radius_m
    if incident.location_status == LocationStatus.RESOLVED:
        return incident.location_precision_m is not None and incident.location_precision_m <= radius_m
    return False


def recompute_matches(session: Session, incident: Incident, radius_m: float) -> list[tuple[str, float]]:
    """Replace the incident's blackspot matches and refresh its geographic risk.

    Uses ST_DWithin / ST_Distance on ``geography`` (metres) and the GiST index on
    ``blackspots.geom``. Returns (risk_level, distance_m) pairs.
    """
    session.execute(delete(IncidentBlackspotMatch).where(IncidentBlackspotMatch.incident_id == incident.id))
    found: list[tuple[str, float]] = []
    if eligible_for_matching(incident, radius_m):
        distance = func.ST_Distance(Blackspot.geom, incident.geom)
        rows = session.execute(
            select(Blackspot.id, Blackspot.risk_level, distance)
            .where(func.ST_DWithin(Blackspot.geom, incident.geom, radius_m))
            .order_by(distance, Blackspot.id)
        ).all()
        for blackspot_id, level, meters in rows:
            session.add(
                IncidentBlackspotMatch(
                    incident_id=incident.id, blackspot_id=blackspot_id, distance_meters=float(meters)
                )
            )
            found.append((level, float(meters)))
    previous = incident.geographic_risk_score
    incident.geographic_risk_score = geographic_risk(found, radius_m)
    incident.review_priority = raise_priority(
        incident.review_priority, previous, incident.geographic_risk_score
    )
    session.flush()
    return found


def match_status(session: Session, incident: Incident, radius_m: float) -> str:
    """unavailable (no blackspot data) | location_unknown | no_match | matched"""
    if not blackspots_exist(session):
        return "unavailable"
    if not eligible_for_matching(incident, radius_m):
        return "location_unknown"
    has_match = session.scalar(
        select(exists().where(IncidentBlackspotMatch.incident_id == incident.id))
    )
    return "matched" if has_match else "no_match"


def incident_ids_near(session: Session, blackspot_id: uuid.UUID, radius_m: float) -> list[uuid.UUID]:
    """Located incidents within the radius of a (new) blackspot, for re-matching after an import."""
    spot = session.get(Blackspot, blackspot_id)
    if spot is None:
        return []
    return list(
        session.scalars(
            select(Incident.id).where(Incident.geom.is_not(None), func.ST_DWithin(Incident.geom, spot.geom, radius_m))
        )
    )
