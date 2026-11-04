"""The ONLY place public data is read.

Every query starts from :func:`published_base`: a ``public_alerts`` row that is ``published``
(which the database trigger only allows for an exact bulletin version carrying a standing human
approval) on an incident whose status is ``published``. Nothing here selects from incident
candidates, reviews, evidence payloads or extraction output.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from geoalchemy2 import Geography, Geometry
from sqlalchemy import Select, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.pagination import PageParams
from app.models import (
    Blackspot,
    BulletinVersion,
    Incident,
    IncidentEvidence,
    PublicAlert,
    Source,
    SourceItem,
)
from app.models.enums import AlertStatus, EvidenceRole, IncidentStatus, LocationStatus, SourceKind
from app.schemas.public import (
    PublicAlertDetail,
    PublicAlertSummary,
    PublicBlackspot,
    PublicPoint,
    PublicSource,
    RouteBlackspot,
    RouteHazard,
)

LAT = func.ST_Y(cast(Incident.geom, Geometry)).label("lat")
LNG = func.ST_X(cast(Incident.geom, Geometry)).label("lng")

# Only these kinds of source are credited publicly (news publishers and official channels);
# social / WhatsApp / manual evidence is never exposed.
PUBLIC_SOURCE_KINDS = (SourceKind.RSS.value, SourceKind.OFFICIAL.value)
PUBLIC_EVIDENCE_ROLES = (EvidenceRole.PRIMARY.value, EvidenceRole.CORROBORATING.value)
MAPPABLE_LOCATION = (LocationStatus.RESOLVED.value, LocationStatus.EDITOR_CONFIRMED.value)
EXACT_MAX_PRECISION_M = 100
COORD_DECIMALS = 4  # ~11 m: never publish more precision than the geocoding supports

NOTICE = (
    "Conditions may have changed since this notice was last updated. "
    "SafeRouteZW publishes reviewed reports only; the absence of an alert does not mean a road is safe."
)
SUMMARY_LENGTH = 240


def published_base() -> Select:
    return (
        select(PublicAlert, BulletinVersion, Incident, LAT, LNG)
        .join(BulletinVersion, BulletinVersion.id == PublicAlert.bulletin_version_id)
        .join(Incident, Incident.id == PublicAlert.incident_id)
        .where(
            PublicAlert.status == AlertStatus.PUBLISHED.value,
            PublicAlert.published_at.is_not(None),
            Incident.status == IncidentStatus.PUBLISHED.value,
        )
    )


def mappable(incident: Incident) -> bool:
    return incident.geom is not None and incident.location_status in MAPPABLE_LOCATION


def precision_label(incident: Incident) -> str:
    exact = (
        incident.location_status == LocationStatus.EDITOR_CONFIRMED.value
        and incident.location_precision_m is not None
        and incident.location_precision_m <= EXACT_MAX_PRECISION_M
    )
    return "exact" if exact else "approximate"


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def make_summary_text(body: str) -> str:
    flat = " ".join(body.split())
    if len(flat) <= SUMMARY_LENGTH:
        return flat
    return flat[:SUMMARY_LENGTH].rsplit(" ", 1)[0].rstrip(",;:.") + "..."


def general_location(alert: PublicAlert, incident: Incident) -> str | None:
    parts = [p for p in (alert.road_name, alert.province) if p]
    if parts:
        return ", ".join(parts)
    text = (incident.location_text or "").strip()
    return text[:120] or None


def load_sources(session: Session, incident_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[PublicSource]]:
    if not incident_ids:
        return {}
    rows = session.execute(
        select(IncidentEvidence.incident_id, Source.name, SourceItem.canonical_url)
        .join(SourceItem, SourceItem.id == IncidentEvidence.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(
            IncidentEvidence.incident_id.in_(incident_ids),
            IncidentEvidence.evidence_role.in_(PUBLIC_EVIDENCE_ROLES),
            Source.kind.in_(PUBLIC_SOURCE_KINDS),
        )
        .order_by(IncidentEvidence.created_at, Source.name)
    ).all()
    out: dict[uuid.UUID, list[PublicSource]] = {}
    seen: set[tuple[uuid.UUID, str]] = set()
    for incident_id, name, url in rows:
        if (incident_id, name) in seen:
            continue
        seen.add((incident_id, name))
        out.setdefault(incident_id, []).append(PublicSource(name=name, url=url))
    return out


def _summary(
    alert: PublicAlert, version: BulletinVersion, incident: Incident, sources: list[PublicSource]
) -> dict[str, Any]:
    assert alert.published_at is not None
    return {
        "id": alert.id,
        "headline": version.headline,
        "summary": make_summary_text(version.body),
        "location": general_location(alert, incident),
        "province": alert.province,
        "road_name": alert.road_name,
        "hazard_type": incident.incident_type,
        "severity": incident.severity,
        "published_at": alert.published_at,
        "updated_at": alert.published_at,
        "has_map_location": mappable(incident),
        "sources": sources,
    }


def build_summaries(session: Session, rows: list[Any]) -> list[PublicAlertSummary]:
    sources = load_sources(session, [row[2].id for row in rows])
    return [PublicAlertSummary(**_summary(a, v, i, sources.get(i.id, []))) for a, v, i, _lat, _lng in rows]


def list_alerts(
    session: Session,
    params: PageParams,
    *,
    q: str | None,
    province: str | None,
    road: str | None,
    hazard_type: str | None,
    since: datetime | None = None,
) -> tuple[list[PublicAlertSummary], int]:
    query = published_base()
    if q:
        pattern = _like(q.strip())
        query = query.where(
            or_(
                BulletinVersion.headline.ilike(pattern),
                BulletinVersion.body.ilike(pattern),
                PublicAlert.road_name.ilike(pattern),
                Incident.location_text.ilike(pattern),
            )
        )
    if province:
        query = query.where(PublicAlert.province == province)
    if road:
        query = query.where(PublicAlert.road_name.ilike(_like(road.strip())))
    if hazard_type:
        query = query.where(Incident.incident_type == hazard_type)
    if since:
        query = query.where(PublicAlert.published_at >= since)
    total = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = session.execute(
        query.order_by(PublicAlert.published_at.desc(), PublicAlert.id.desc())
        .limit(params.page_size)
        .offset(params.offset)
    ).all()
    return build_summaries(session, rows), total


def get_alert(session: Session, alert_id: uuid.UUID) -> PublicAlertDetail | None:
    row = session.execute(published_base().where(PublicAlert.id == alert_id)).first()
    if row is None:
        return None
    alert, version, incident, lat, lng = row
    sources = load_sources(session, [incident.id])
    point = None
    if mappable(incident) and lat is not None and lng is not None:
        point = PublicPoint(
            latitude=round(lat, COORD_DECIMALS),
            longitude=round(lng, COORD_DECIMALS),
            precision=precision_label(incident),
        )
    return PublicAlertDetail(
        **_summary(alert, version, incident, sources.get(incident.id, [])),
        body=version.body,
        point=point,
        notice=NOTICE,
    )


def recent_summary(session: Session, days: int, limit: int) -> tuple[int, list[PublicAlertSummary], datetime | None]:
    since = datetime.now(UTC) - timedelta(days=days)
    query = published_base().where(PublicAlert.published_at >= since)
    count = session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    rows = session.execute(
        query.order_by(PublicAlert.published_at.desc(), PublicAlert.id.desc()).limit(limit)
    ).all()
    latest = session.scalar(
        select(func.max(PublicAlert.published_at)).where(PublicAlert.status == AlertStatus.PUBLISHED.value)
    )
    return count, build_summaries(session, rows), latest


def map_rows(
    session: Session, *, hazard_type: str | None, severity: str | None, since: datetime | None
) -> tuple[list[Any], int]:
    """Published alerts with a reliable position, plus a count of those without one."""
    base = published_base()
    if hazard_type:
        base = base.where(Incident.incident_type == hazard_type)
    if severity:
        base = base.where(Incident.severity == severity)
    if since:
        base = base.where(PublicAlert.published_at >= since)
    located = base.where(Incident.geom.is_not(None), Incident.location_status.in_(MAPPABLE_LOCATION))
    rows = session.execute(located.order_by(PublicAlert.published_at.desc(), PublicAlert.id.desc())).all()
    total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    return list(rows), total - len(rows)


def blackspot_dto(b: Blackspot, lat: float, lng: float) -> PublicBlackspot:
    return PublicBlackspot(
        id=b.id,
        name=b.name,
        description=b.description,
        risk_level=b.risk_level,
        latitude=round(lat, COORD_DECIMALS),
        longitude=round(lng, COORD_DECIMALS),
        source_name=b.source_name,
        source_reference=b.source_reference,
        observation_period_start=b.observation_period_start.isoformat() if b.observation_period_start else None,
        observation_period_end=b.observation_period_end.isoformat() if b.observation_period_end else None,
    )


def list_blackspots(session: Session) -> list[PublicBlackspot]:
    """Only sourced rows (``source_name`` is NOT NULL by constraint)."""
    lat = func.ST_Y(cast(Blackspot.geom, Geometry))
    lng = func.ST_X(cast(Blackspot.geom, Geometry))
    rows = session.execute(select(Blackspot, lat, lng).order_by(Blackspot.name, Blackspot.id)).all()
    return [blackspot_dto(b, la, ln) for b, la, ln in rows]


# --- route overlay -----------------------------------------------------------------------------


def _route_geography(geometry: dict[str, Any]):
    geom = func.ST_SetSRID(func.ST_GeomFromGeoJSON(json.dumps(geometry)), 4326)
    return cast(geom, Geography)


def hazards_near_route(session: Session, geometry: dict[str, Any], buffer_m: float) -> list[RouteHazard]:
    """Published alerts with a reliable position within ``buffer_m`` of the route (PostGIS)."""
    route = _route_geography(geometry)
    distance = func.ST_Distance(Incident.geom, route).label("distance")
    rows = session.execute(
        published_base()
        .add_columns(distance)
        .where(
            Incident.geom.is_not(None),
            Incident.location_status.in_(MAPPABLE_LOCATION),
            func.ST_DWithin(Incident.geom, route, buffer_m),
        )
        .order_by(distance, PublicAlert.id)
    ).all()
    sources = load_sources(session, [r[2].id for r in rows])
    out: list[RouteHazard] = []
    for alert, version, incident, _lat, _lng, meters in rows:
        assert alert.published_at is not None
        out.append(
            RouteHazard(
                alert_id=alert.id,
                headline=version.headline,
                hazard_type=incident.incident_type,
                severity=incident.severity,
                distance_from_route_m=round(float(meters), 1),
                location_precision=precision_label(incident),
                source_names=[s.name for s in sources.get(incident.id, [])],
                published_at=alert.published_at,
                updated_at=alert.published_at,
                is_closure=False,
                alert_url=f"/public/alerts/{alert.id}",
            )
        )
    return out


def blackspots_near_route(session: Session, geometry: dict[str, Any], buffer_m: float) -> list[RouteBlackspot]:
    route = _route_geography(geometry)
    distance = func.ST_Distance(Blackspot.geom, route).label("distance")
    lat = func.ST_Y(cast(Blackspot.geom, Geometry))
    lng = func.ST_X(cast(Blackspot.geom, Geometry))
    rows = session.execute(
        select(Blackspot, lat, lng, distance)
        .where(func.ST_DWithin(Blackspot.geom, route, buffer_m))
        .order_by(distance, Blackspot.id)
    ).all()
    return [
        RouteBlackspot(
            id=b.id,
            name=b.name,
            risk_level=b.risk_level,
            distance_from_route_m=round(float(m), 1),
            source_name=b.source_name,
            latitude=round(la, COORD_DECIMALS),
            longitude=round(ln, COORD_DECIMALS),
        )
        for b, la, ln, m in rows
    ]
