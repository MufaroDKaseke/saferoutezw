"""Public route planning: resolve places, ask the routing engine, overlay published hazards.

Rules:
* geometry always comes from the routing provider, never from us;
* hazards are published alerts with a reliable position, found with PostGIS ``ST_DWithin``;
* blackspots are a separate, historical list;
* nothing here says a route is safe, and there is no automatic rerouting around hazards.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import PublicAlert
from app.models.enums import AlertStatus
from app.repositories import public as repo
from app.schemas.public import PlaceInput, ResolvedPlace, RoutePlanRequest, RoutePlanResponse
from app.services.routing.base import GeocodedPlace, RoutingError, RoutingProvider, inside_zimbabwe

DISCLAIMER = (
    "This is a planning aid based on reviewed SafeRouteZW alerts and a routing engine estimate. "
    "No alerts near a route does not mean the route is safe. Conditions change; use your own judgement."
)
DURATION_NOTE = "Routing-engine estimate without live traffic."
LOW_CONFIDENCE = 0.6


def _resolve(provider: RoutingProvider, place: PlaceInput, role: str, warnings: list[str]) -> ResolvedPlace:
    if place.latitude is not None and place.longitude is not None:
        if not inside_zimbabwe(place.latitude, place.longitude):
            raise RoutingError(f"The {role} is outside Zimbabwe.")
        return ResolvedPlace(label="Chosen point", latitude=place.latitude, longitude=place.longitude)
    query = (place.query or "").strip()
    if len(query) < 2:
        raise RoutingError(f"Enter a {role}.")
    found: GeocodedPlace = provider.geocode(query)
    if found.confidence is not None and found.confidence < LOW_CONFIDENCE:
        warnings.append(f"The {role} '{query[:60]}' was matched with low confidence. Check it on the map.")
    return ResolvedPlace(label=found.label, latitude=found.latitude, longitude=found.longitude)


def plan_route(
    session: Session, provider: RoutingProvider, settings: Settings, request: RoutePlanRequest
) -> RoutePlanResponse:
    warnings: list[str] = []
    places = [
        _resolve(provider, request.origin, "origin", warnings),
        *[_resolve(provider, stop, f"stop {i + 1}", warnings) for i, stop in enumerate(request.stops)],
        _resolve(provider, request.destination, "destination", warnings),
    ]
    if request.optimise:
        warnings.append("Route optimisation is not supported. Stops were kept in the order you gave.")

    route = provider.route([(p.latitude, p.longitude) for p in places], request.mode)
    warnings.extend(route.warnings)

    buffer_m = settings.route_hazard_buffer_m
    hazards = repo.hazards_near_route(session, route.geometry, buffer_m)
    blackspots = repo.blackspots_near_route(session, route.geometry, buffer_m)
    if not hazards:
        warnings.append(
            "No published alerts were found near this route. This does not mean the road is safe."
        )
    updated: datetime | None = session.scalar(
        select(func.max(PublicAlert.published_at)).where(PublicAlert.status == AlertStatus.PUBLISHED.value)
    )
    return RoutePlanResponse(
        provider=route.provider,
        places=places,
        geometry=route.geometry,
        distance_m=route.distance_m,
        duration_s=route.duration_s,
        duration_note=DURATION_NOTE,
        hazards=[h for h in hazards if not h.is_closure],
        closures=[h for h in hazards if h.is_closure],
        blackspots=blackspots,
        hazard_buffer_m=buffer_m,
        warnings=warnings,
        disclaimer=DISCLAIMER,
        data_updated_at=updated,
    )
