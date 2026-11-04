"""Route planning with a mock provider: hazard overlay, honesty and failure handling."""

import pytest
from geoalchemy2 import WKTElement

from app.models import Blackspot
from app.services.routing.mock import MockRoutingProvider
from public_helpers import PLACES, configure, make_published_alert, mock_routing  # noqa: F401

pytestmark = pytest.mark.usefixtures("migrated_engine")

URL = "/api/v1/public/routes/plan"
# A point on the straight Harare -> Mutare line (the mock provider draws straight lines).
ON_ROUTE = (-18.216, 31.6)


def plan(client, origin="Harare", destination="Mutare", **extra):
    return client.post(URL, json={"origin": {"query": origin}, "destination": {"query": destination}, **extra})


def test_point_to_point_route_with_published_hazard_near_it(client, session, configure, mock_routing):
    configure(mock_routing)
    alert, _, _ = make_published_alert(session, lat=ON_ROUTE[0], lng=ON_ROUTE[1])
    data = plan(client).json()
    assert data["provider"] == "mock" and data["geometry"]["type"] == "LineString"
    assert data["distance_m"] > 100_000 and "without live traffic" in data["duration_note"]
    assert [h["alert_id"] for h in data["hazards"]] == [str(alert.id)]
    hazard = data["hazards"][0]
    assert hazard["distance_from_route_m"] < 500 and hazard["location_precision"] == "exact"
    assert hazard["source_names"] and hazard["alert_url"] == f"/public/alerts/{alert.id}"
    assert data["blackspots"] == [] and data["data_updated_at"]


def test_empty_results_never_claim_safety(client, session, configure, mock_routing):
    configure(mock_routing)
    data = plan(client).json()
    assert data["hazards"] == [] and data["blackspots"] == []
    assert any("does not mean the road is safe" in w for w in data["warnings"])
    assert "does not mean the route is safe" in data["disclaimer"]
    assert "is safe" not in data["disclaimer"].replace("does not mean the route is safe", "")


def test_unpublished_far_and_unlocated_alerts_are_ignored(client, session, configure, mock_routing):
    configure(mock_routing)
    ready, _, _ = make_published_alert(session, lat=ON_ROUTE[0], lng=ON_ROUTE[1])
    ready.status = "ready"
    session.commit()
    make_published_alert(session, lat=-20.13, lng=28.63, headline="[SYNTHETIC] Far away in Bulawayo")
    make_published_alert(
        session, lat=None, lng=None, location_status="unresolved", headline="[SYNTHETIC] Unplaced"
    )
    make_published_alert(
        session, lat=ON_ROUTE[0], lng=ON_ROUTE[1], location_status="ambiguous", headline="[SYNTHETIC] Ambiguous"
    )
    assert plan(client).json()["hazards"] == []


def test_blackspots_are_listed_separately_from_alerts(client, session, configure, mock_routing):
    configure(mock_routing)
    session.add(
        Blackspot(
            name="[SYNTHETIC] Test blackspot", geom=WKTElement(f"POINT({ON_ROUTE[1]} {ON_ROUTE[0]})", srid=4326),
            source_name="Synthetic test dataset", risk_level="high",
        )
    )
    session.commit()
    data = plan(client).json()
    assert data["hazards"] == [] and len(data["blackspots"]) == 1
    assert data["blackspots"][0]["source_name"] == "Synthetic test dataset"


def test_multiple_stops_keep_the_requested_order(client, configure, mock_routing):
    configure(mock_routing)
    body = {
        "origin": {"query": "Harare"}, "destination": {"query": "Bulawayo"},
        "stops": [{"query": "Marondera"}, {"latitude": -18.5, "longitude": 31.9}], "optimise": True,
    }
    data = client.post(URL, json=body).json()
    assert [p["label"] for p in data["places"]][0] == "Harare" and len(data["places"]) == 4
    assert mock_routing.calls[-1][1] == PLACES["marondera"] and mock_routing.calls[-1][2] == (-18.5, 31.9)
    assert any("optimisation is not supported" in w for w in data["warnings"])


def test_more_than_five_stops_is_rejected(client, configure, mock_routing):
    configure(mock_routing)
    stops = [{"query": "Marondera"}] * 6
    r = client.post(URL, json={"origin": {"query": "Harare"}, "destination": {"query": "Mutare"}, "stops": stops})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "origin",
    [{"query": "Atlantis"}, {"query": ""}, {}, {"latitude": 51.5, "longitude": -0.12}],
)
def test_invalid_locations_are_rejected_without_a_route(client, configure, mock_routing, origin):
    configure(mock_routing)
    r = client.post(URL, json={"origin": origin, "destination": {"query": "Mutare"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "ROUTE_INPUT_INVALID"
    assert mock_routing.calls == []  # no geometry was ever produced


def test_provider_failure_is_a_clean_503(client, configure):
    configure(MockRoutingProvider(PLACES, fail="unavailable"))
    r = plan(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ROUTING_UNAVAILABLE"
    assert "Traceback" not in r.text


def test_missing_routing_configuration_is_unavailable_not_fake(client, configure):
    configure(routing_provider="none")
    from app.main import app
    from app.api.v1.public import routing_provider

    app.dependency_overrides.pop(routing_provider, None)
    r = plan(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "ROUTING_UNAVAILABLE"


def test_planning_is_rate_limited(client, configure, mock_routing):
    configure(mock_routing, public_write_rate_limit_per_minute=2)
    assert plan(client).status_code == 200 and plan(client).status_code == 200
    assert plan(client).status_code == 429
