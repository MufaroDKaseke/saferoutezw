"""Shared fixtures/builders for the public API, routing, subscription and notification tests.

Everything here is synthetic. Messaging and routing are always mocks: no test can send a real
SMS/WhatsApp message or call a real routing service.
"""

from __future__ import annotations

import pytest
from geoalchemy2 import WKTElement

import db_factories as f
from app.api.rate_limit import reset_rate_limits
from app.core.config import Settings, get_settings
from app.services.notifications import reset_mock_providers
from app.services.routing import RoutingProvider
from app.services.routing.mock import MockRoutingProvider

PLACES = {
    "harare": (-17.8292, 31.0522),
    "mutare": (-18.9707, 32.6709),
    "marondera": (-18.1853, 31.5519),
    "bulawayo": (-20.1325, 28.6265),
}


def make_settings(**overrides) -> Settings:
    values = {
        "routing_provider": "mock",
        "notification_provider": "mock",
        "public_write_rate_limit_per_minute": 1000,
        "public_rate_limit_per_minute": 1000,
        "otp_resend_cooldown_seconds": 0,
        "otp_max_per_hour": 100,
        "subscription_corridors": "A3 Harare-Mutare, A5 Harare-Bulawayo",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def configure(client):
    """Install settings (and optionally a routing provider) on the running app."""
    from app.api.v1.public import routing_provider
    from app.main import app

    reset_rate_limits()
    reset_mock_providers()

    def apply(provider: RoutingProvider | None = None, **overrides) -> Settings:
        settings = make_settings(**overrides)
        app.dependency_overrides[get_settings] = lambda: settings
        if provider is not None:
            app.dependency_overrides[routing_provider] = lambda: provider
        return settings

    apply()
    yield apply
    reset_rate_limits()
    reset_mock_providers()


@pytest.fixture
def mock_routing() -> MockRoutingProvider:
    return MockRoutingProvider(PLACES)


def make_published_alert(
    session,
    *,
    headline: str = "[SYNTHETIC] Crash on the Harare-Mutare road",
    body: str = "[SYNTHETIC] A collision was reported. Drive with care.",
    lat: float | None = -18.2,
    lng: float | None = 31.6,
    location_status: str = "editor_confirmed",
    precision_m: float | None = 50,
    province: str | None = "Mashonaland East",
    road_name: str | None = "A3 Harare-Mutare",
    incident_type: str = "collision",
    source_kind: str | None = "rss",
):
    """Build a fully approved + published alert directly (bypassing the API, with real triggers)."""
    editor = f.make_user(session, "editor")
    incident = f.make_incident(
        session,
        incident_type=incident_type,
        severity="serious",
        status="under_review",
        location_text="Near Marondera",
        location_status=location_status,
        location_precision_m=precision_m,
        geom=WKTElement(f"POINT({lng} {lat})", srid=4326) if lat is not None and lng is not None else None,
    )
    from app.models import BulletinVersion

    bulletin = BulletinVersion(
        incident_id=incident.id, version_number=1, headline=headline, body=body, created_by=editor.id
    )
    session.add(bulletin)
    session.flush()
    review = f.make_review(session, incident, bulletin, editor)
    incident.status = "published"
    session.flush()
    from datetime import UTC, datetime

    alert = f.make_alert(
        session, incident, bulletin, review,
        status="published", published_at=datetime.now(UTC), province=province, road_name=road_name,
    )
    if source_kind:
        source = f.make_source(session, kind=source_kind)
        item = f.make_source_item(session, source)
        from app.models import IncidentEvidence

        session.add(IncidentEvidence(incident_id=incident.id, source_item_id=item.id, evidence_role="primary"))
        session.flush()
    session.commit()
    return alert, incident, bulletin
