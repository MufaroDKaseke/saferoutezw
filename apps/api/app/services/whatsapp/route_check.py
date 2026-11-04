"""Function 3 - check a route for published road alerts.

Reuses, unchanged: the geocoder for place candidates, the public routing service
(``route_planning.plan_route``) for distance, duration and hazards near the route, and its
published-only PostGIS query. This module only asks the questions and formats a short reply from
the real response. If routing fails the user is told so; nothing is estimated or invented.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.whatsapp.messages import Choice, list_message, text_message
from app.schemas.public import PlaceInput, RoutePlanRequest, RoutePlanResponse
from app.services.geolocation import GeocoderError, build_geocoder
from app.services.route_planning import plan_route
from app.services.routing.base import RoutingError, RoutingUnavailable, inside_zimbabwe
from app.services.whatsapp.context import Ctx, Place, PlaceLookupUnavailable, PlaceResolver

log = logging.getLogger(__name__)

FLOW = "route"
MAX_CANDIDATES = 5
MAX_HAZARDS_SHOWN = 3
MAX_QUERY = 120

ORIGIN_PROMPT = "Check a route\n\nWhere are you starting from? Type a town, city or place (for example: Harare)."
DESTINATION_PROMPT = "Where are you going? Type a town, city or place (for example: Mutare)."
UNAVAILABLE = "Route checking is temporarily unavailable. Please try again later. Reply MENU for options."
DISCLAIMER = "Information may be incomplete or outdated. No reported alerts does not guarantee the road is safe."


# --------------------------------------------------------------------------- place resolvers


class GeocoderResolver(PlaceResolver):
    """Candidates from the configured geocoder (Zimbabwe only, at most 5)."""

    def __init__(self, settings: Settings) -> None:
        self._geocoder = build_geocoder(settings)

    def candidates(self, query: str) -> list[Place]:
        if self._geocoder is None:
            raise PlaceLookupUnavailable("no geocoder configured")
        try:
            results = self._geocoder.geocode(query)
        except GeocoderError as error:
            raise PlaceLookupUnavailable(str(error)) from error
        places: list[Place] = []
        for r in results:
            if not inside_zimbabwe(r.latitude, r.longitude) or any(p.label == r.label for p in places):
                continue
            places.append(Place(r.label, r.latitude, r.longitude))
        return places[:MAX_CANDIDATES]


class StaticResolver(PlaceResolver):
    """Fixed places, for tests and the offline simulator. A value may be one point or several."""

    def __init__(self, places: dict[str, list[Place]], *, fail: bool = False) -> None:
        self._places = {k.lower(): v for k, v in places.items()}
        self._fail = fail

    def candidates(self, query: str) -> list[Place]:
        if self._fail:
            raise PlaceLookupUnavailable("simulated outage")
        return list(self._places.get(query.strip().lower(), []))


# --------------------------------------------------------------------------- flow


def prompt(ctx: Ctx) -> None:
    step = ctx.conv.step
    if step == "origin":
        ctx.say(text_message(ORIGIN_PROMPT))
    elif step == "destination":
        ctx.say(text_message(DESTINATION_PROMPT))
    elif step in ("origin_pick", "destination_pick"):
        _ask_pick(ctx, which="origin" if step == "origin_pick" else "destination")
    else:
        start(ctx)


def start(ctx: Ctx) -> None:
    ctx.goto(FLOW, "origin", origin=None, destination=None, candidates=[])
    prompt(ctx)


def back(ctx: Ctx) -> bool:
    previous = {"origin_pick": "origin", "destination": "origin", "destination_pick": "destination"}.get(ctx.conv.step)
    if previous is None:
        return False
    ctx.goto(FLOW, previous, candidates=[])
    prompt(ctx)
    return True


def handle(ctx: Ctx) -> None:
    step, event = ctx.conv.step, ctx.event
    if event.is_media or event.is_location and step not in ("origin", "destination"):
        ctx.say(text_message("Please reply with text for this step."))
        return prompt(ctx)

    if step in ("origin", "destination"):
        if event.is_location:  # a pin is an unambiguous place
            lat, lon = event.latitude, event.longitude
            if lat is None or lon is None or not inside_zimbabwe(lat, lon):
                ctx.say(text_message("That pin is outside Zimbabwe. Please type a place in Zimbabwe."))
                return
            return _accept(ctx, step, Place("Shared location", lat, lon))
        query = event.free_text
        if not event.is_text or len(query) < 2 or len(query) > MAX_QUERY:
            ctx.say(text_message("Please type a place name (2–120 characters)."))
            return
        try:
            candidates = ctx.deps.resolver.candidates(query)
        except PlaceLookupUnavailable:
            ctx.reset()
            ctx.say(text_message(UNAVAILABLE))
            return
        if not candidates:
            ctx.say(text_message(f"I couldn't find “{query[:60]}” in Zimbabwe. Try a nearby town or a different spelling."))
            return
        if len(candidates) == 1:
            return _accept(ctx, step, candidates[0])
        ctx.goto(FLOW, f"{step}_pick", candidates=[[c.label, c.latitude, c.longitude] for c in candidates])
        return prompt(ctx)

    if step in ("origin_pick", "destination_pick"):
        which = "origin" if step == "origin_pick" else "destination"
        candidates = ctx.data.get("candidates") or []
        choice = event.choice
        if choice.startswith("C:"):  # a tapped list row, "C:<origin|destination>:<n>"
            parts = choice.split(":")
            if len(parts) != 3 or parts[1].lower() != which:
                return prompt(ctx)  # a stale row from an earlier question
            choice = parts[2]
        if choice == "0":
            ctx.goto(FLOW, which, candidates=[])
            return prompt(ctx)
        if choice.isdigit() and 1 <= int(choice) <= len(candidates):
            label, lat, lon = candidates[int(choice) - 1]
            return _accept(ctx, which, Place(label, lat, lon))
        ctx.say(text_message("Please choose one of the places in the list."))
        return prompt(ctx)

    start(ctx)


def _ask_pick(ctx: Ctx, *, which: str) -> None:
    candidates = ctx.data.get("candidates") or []
    rows = [Choice(f"c:{which}:{i}", _short(label, 24), label[:72]) for i, (label, _, _) in enumerate(candidates, 1)]
    rows.append(Choice(f"c:{which}:0", "None of these", "Search again"))
    lines = [f"{i}. {label}" for i, (label, _, _) in enumerate(candidates, 1)]
    noun = "starting point" if which == "origin" else "destination"
    ctx.say(
        list_message(
            f"Several places match. Which is your {noun}?\n\n" + "\n".join(lines) + "\n0. None of these\n\nPick one, or reply with its number.",
            rows,
            "Choose place",
        )
    )


def _accept(ctx: Ctx, step: str, place: Place) -> None:
    which = "origin" if step.startswith("origin") else "destination"
    ctx.set(**{which: [place.label, place.latitude, place.longitude]}, candidates=[])
    if which == "origin":
        ctx.goto(FLOW, "destination")
        return prompt(ctx)
    return finish(ctx)


# --------------------------------------------------------------------------- result


def _short(label: str, limit: int) -> str:
    label = " ".join(label.split())
    return label if len(label) <= limit else label[: limit - 1].rstrip() + "…"


def _place_name(label: str) -> str:
    """'Harare, Harare Province, Zimbabwe' -> 'Harare' (what the reader needs)."""
    return _short(label.split(",")[0].strip() or label, 40)


def _distance(metres: float) -> str:
    km = metres / 1000
    return f"{km:.1f} km" if km < 10 else f"{round(km)} km"


def _duration(seconds: float) -> str:
    minutes = max(1, round(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def format_result(plan: RoutePlanResponse, origin: str, destination: str, base_url: str) -> str:
    link = f"{base_url.rstrip('/')}/public/routes?" + urlencode({"from": origin, "to": destination})
    hazards = plan.hazards + plan.closures
    lines = [
        "SafeRouteZW — Route Check",
        "",
        f"{origin} → {destination}",
        "",
        f"Distance: {_distance(plan.distance_m)}",
        f"Estimated drive: {_duration(plan.duration_s)} (routing estimate, no live traffic)",
        "",
        f"Published road alerts: {len(hazards)}",
    ]
    for hazard in hazards[:MAX_HAZARDS_SHOWN]:
        lines.append(f"• {_short(hazard.headline, 90)} ({hazard.hazard_type}, {hazard.severity})")
    if len(hazards) > MAX_HAZARDS_SHOWN:
        lines.append(f"+ {len(hazards) - MAX_HAZARDS_SHOWN} more on the website")
    lines += ["", f"View details: {link}", "", DISCLAIMER, "", "Reply MENU for options."]
    return "\n".join(lines)


def run_plan(session: Session, settings: Settings, provider, origin: Place, destination: Place) -> RoutePlanResponse:
    request = RoutePlanRequest(
        origin=PlaceInput(latitude=origin.latitude, longitude=origin.longitude),
        destination=PlaceInput(latitude=destination.latitude, longitude=destination.longitude),
    )
    return plan_route(session, provider, settings, request)


def finish(ctx: Ctx) -> None:
    data = ctx.data
    origin, destination = Place(*data["origin"]), Place(*data["destination"])
    ctx.reset()
    try:
        provider = ctx.deps.routing_provider(ctx.settings)
        plan = run_plan(ctx.session, ctx.settings, provider, origin, destination)
    except RoutingUnavailable:
        log.warning("WhatsApp route check: routing unavailable")
        ctx.say(text_message(UNAVAILABLE))
        return
    except RoutingError:
        ctx.say(text_message("I couldn't find a drivable route between those places. Reply MENU to try again."))
        return
    ctx.say(text_message(format_result(plan, _place_name(origin.label), _place_name(destination.label), ctx.settings.public_web_base_url)))
