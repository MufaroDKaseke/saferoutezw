"""Production wiring of the bot's external dependencies."""

from __future__ import annotations

from app.core.config import Settings
from app.services.routing.factory import get_routing_provider
from app.services.whatsapp.context import Deps
from app.services.whatsapp.route_check import GeocoderResolver


def default_deps(settings: Settings) -> Deps:
    return Deps(resolver=GeocoderResolver(settings), routing_provider=get_routing_provider)
