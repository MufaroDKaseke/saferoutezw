from __future__ import annotations

from app.core.config import Settings
from app.services.routing.base import RoutingProvider, RoutingUnavailable


def get_routing_provider(settings: Settings) -> RoutingProvider:
    """Build the configured provider, or raise RoutingUnavailable. Never falls back to fake routes."""
    if settings.routing_provider == "geoapify":
        from app.services.routing.geoapify import GeoapifyProvider

        return GeoapifyProvider(settings)
    if settings.routing_provider == "mock":
        from app.services.routing.mock import MockRoutingProvider

        return MockRoutingProvider()
    raise RoutingUnavailable("Route planning is not configured.")
