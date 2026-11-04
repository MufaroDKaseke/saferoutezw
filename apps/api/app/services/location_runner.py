"""Background step: propose a position for incident candidates that have only location text.

Runs after the article pipeline. It only touches incidents that have never been attempted
(``location_updated_at IS NULL``) and never overrides an editor's decision. Without a
configured geocoder nothing happens and incidents simply stay ``unresolved``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from geoalchemy2 import WKTElement
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Incident
from app.models.enums import IncidentStatus, LocationStatus
from app.services.audit import record_audit
from app.services.blackspot_matching import recompute_matches
from app.services.geolocation import GeocoderError, GeocoderProvider, resolve_location

log = logging.getLogger(__name__)

OPEN_STATUSES = (IncidentStatus.CANDIDATE.value, IncidentStatus.UNDER_REVIEW.value)


@dataclass
class LocationSummary:
    attempted: int = 0
    resolved: int = 0
    ambiguous: int = 0
    unresolved: int = 0
    provider_errors: int = 0
    stopped_early: bool = False

    def __str__(self) -> str:
        return (
            f"Geolocation: {self.attempted} attempted, {self.resolved} resolved, "
            f"{self.ambiguous} ambiguous, {self.unresolved} unresolved, {self.provider_errors} errors"
        )


def apply_resolution(incident: Incident, resolution, now: datetime) -> None:
    incident.location_status = resolution.status.value
    incident.location_precision_m = resolution.precision_meters
    incident.location_source = resolution.source
    incident.location_method = resolution.method
    incident.location_candidates = resolution.candidates or None
    incident.location_note = resolution.note
    incident.location_updated_at = now
    if resolution.status == LocationStatus.RESOLVED:
        incident.geom = WKTElement(f"POINT({resolution.longitude} {resolution.latitude})", srid=4326)
    else:
        incident.geom = None


class LocationRunner:
    def __init__(self, engine: Engine, provider: GeocoderProvider, settings: Settings, batch_size: int = 25) -> None:
        self._engine = engine
        self._provider = provider
        self._settings = settings
        self._batch_size = batch_size

    def run(self) -> LocationSummary:
        summary = LocationSummary()
        with Session(self._engine) as session:
            ids = list(
                session.scalars(
                    select(Incident.id)
                    .where(
                        Incident.location_updated_at.is_(None),
                        Incident.location_status == LocationStatus.UNRESOLVED.value,
                        Incident.status.in_(OPEN_STATUSES),
                    )
                    .order_by(Incident.created_at)
                    .limit(self._batch_size)
                )
            )
        for incident_id in ids:
            with Session(self._engine) as session:
                incident = session.get(Incident, incident_id, with_for_update=True)
                if incident is None or incident.location_updated_at is not None:
                    continue  # another worker or an editor got there first
                try:
                    resolution = resolve_location(incident.location_text, self._provider, self._settings)
                except GeocoderError as exc:
                    summary.provider_errors += 1
                    log.warning("Geocoder error: %s", exc)
                    if exc.fatal:
                        summary.stopped_early = True
                        break
                    continue  # try again next cycle
                summary.attempted += 1
                apply_resolution(incident, resolution, datetime.now(UTC))
                if resolution.status == LocationStatus.RESOLVED:
                    recompute_matches(session, incident, self._settings.blackspot_match_radius_m)
                record_audit(
                    session,
                    actor_id=None,
                    action="incident.location_proposed",
                    entity_type="incident",
                    entity_id=incident.id,
                    details={"status": resolution.status.value, "method": resolution.method},
                )
                session.commit()
                setattr(summary, resolution.status.value, getattr(summary, resolution.status.value) + 1)
        return summary
