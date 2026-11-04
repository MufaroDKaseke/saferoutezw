"""Geolocation (providers, resolution rules, runner), blackspot matching, scoring, map, import."""

import importlib.util
import io
import sys
from pathlib import Path

import httpx
import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import select

import db_factories as f
from api_helpers import sign_in
from app.core.config import Settings
from app.models import AuditEvent, Blackspot, Incident, IncidentBlackspotMatch
from app.models.enums import LocationStatus
from app.services import scoring
from app.services.blackspot_matching import recompute_matches
from app.services.geolocation import (
    GeocodeResult,
    GeocoderError,
    GoogleGeocoder,
    build_geocoder,
    mentions_kilometre_peg,
    parse_google_results,
    resolve_location,
)
from app.services.location_runner import LocationRunner

pytestmark = pytest.mark.usefixtures("migrated_engine")

_spec = importlib.util.spec_from_file_location(
    "import_blackspots", Path(__file__).resolve().parents[1] / "scripts" / "import_blackspots.py"
)
_script = importlib.util.module_from_spec(_spec)
sys.modules["import_blackspots"] = _script  # dataclasses look the module up by name
_spec.loader.exec_module(_script)
parse_rows = _script.parse_rows

V1 = "/api/v1"
HARARE = (-17.8292, 31.0522)  # lat, lng
METRE_IN_DEGREES = 1 / 111_320


def point(lat, lng):
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def offset_north(metres):
    return point(HARARE[0] + metres * METRE_IN_DEGREES, HARARE[1])


class FakeProvider:
    source = "Fake gazetteer"
    method = "fake_lookup"

    def __init__(self, results=None, error: GeocoderError | None = None):
        self.results, self.error, self.queries = results or [], error, []

    def geocode(self, query):
        self.queries.append(query)
        if self.error:
            raise self.error
        return self.results


def result(label="Harare CBD", lat=HARARE[0], lng=HARARE[1], precision=40.0, partial=False):
    return GeocodeResult(label, lat, lng, precision, "ROOFTOP", partial)


@pytest.fixture
def cfg() -> Settings:
    return Settings(_env_file=None)


# --- resolution rules -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["120km peg along Harare-Masvingo Road", "at the 45 km mark near Chivhu", "peg 85", "KM 120 Beitbridge road", "the 12 kilometre peg"],
)
def test_kilometre_pegs_are_never_geocoded(cfg, text):
    provider = FakeProvider([result()])
    resolution = resolve_location(text, provider, cfg)
    assert resolution.status == LocationStatus.UNRESOLVED and resolution.latitude is None
    assert "Kilometre" in resolution.note and provider.queries == []


@pytest.mark.parametrize("text", ["near Mbudzi roundabout, Harare", "Rusape-Nyanga Road", "pegasus bus terminal"])
def test_ordinary_places_are_not_mistaken_for_pegs(text):
    assert not mentions_kilometre_peg(text)


def test_blank_text_is_unresolved_without_calling_the_provider(cfg):
    provider = FakeProvider([result()])
    assert resolve_location("  ", provider, cfg).status == LocationStatus.UNRESOLVED
    assert resolve_location(None, provider, cfg).status == LocationStatus.UNRESOLVED
    assert provider.queries == []


def test_one_precise_result_is_resolved_with_alternatives_kept(cfg):
    resolution = resolve_location("Harare CBD", FakeProvider([result()]), cfg)
    assert resolution.status == LocationStatus.RESOLVED
    assert (resolution.latitude, resolution.longitude) == HARARE and resolution.precision_meters == 40.0
    assert resolution.method == "fake_lookup" and resolution.source == "Fake gazetteer"
    assert resolution.candidates[0]["label"] == "Harare CBD"


def test_several_partial_or_broad_results_are_ambiguous_and_set_no_point(cfg):
    several = resolve_location("Mbudzi", FakeProvider([result("Mbudzi, Harare"), result("Mbudzi, Mutare", -18.97, 32.67)]), cfg)
    partial = resolve_location("Mbudzi", FakeProvider([result(partial=True)]), cfg)
    broad = resolve_location("Mashonaland", FakeProvider([result(precision=90_000)]), cfg)
    unknown_extent = resolve_location("Somewhere", FakeProvider([result(precision=None)]), cfg)
    for resolution in (several, partial, broad, unknown_extent):
        assert resolution.status == LocationStatus.AMBIGUOUS
        assert resolution.latitude is None and resolution.longitude is None and resolution.candidates
    assert len(several.candidates) == 2


def test_no_match_is_unresolved(cfg):
    resolution = resolve_location("Nowhere Road", FakeProvider([]), cfg)
    assert resolution.status == LocationStatus.UNRESOLVED and resolution.candidates == []


# --- Google provider -------------------------------------------------------------------------------


def google_client(payload, status=200, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


GOOGLE_OK = {
    "status": "OK",
    "results": [
        {
            "formatted_address": "Samora Machel Ave, Harare, Zimbabwe",
            "partial_match": False,
            "geometry": {
                "location": {"lat": -17.83, "lng": 31.05},
                "location_type": "GEOMETRIC_CENTER",
                "viewport": {"northeast": {"lat": -17.8295, "lng": 31.0505}, "southwest": {"lat": -17.8305, "lng": 31.0495}},
            },
        },
        {"formatted_address": "broken result"},
    ],
}


def test_google_results_are_parsed_and_malformed_ones_skipped():
    parsed = parse_google_results(GOOGLE_OK)
    assert len(parsed) == 1 and parsed[0].label.startswith("Samora Machel")
    assert 20 < parsed[0].precision_meters < 100 and parsed[0].match_type == "GEOMETRIC_CENTER"


def test_google_geocoder_restricts_to_zimbabwe_and_returns_results():
    seen = []
    geocoder = GoogleGeocoder("secret-key", client=google_client(GOOGLE_OK, seen=seen))
    assert len(geocoder.geocode("Samora Machel Ave")) == 1
    params = dict(seen[0].url.params)
    assert params["region"] == "zw" and params["components"] == "country:ZW" and params["address"] == "Samora Machel Ave"


@pytest.mark.parametrize(
    "payload, fatal",
    [({"status": "REQUEST_DENIED"}, True), ({"status": "OVER_QUERY_LIMIT"}, False), ({"status": "UNKNOWN_ERROR"}, False)],
)
def test_google_errors_are_classified(payload, fatal):
    with pytest.raises(GeocoderError) as caught:
        GoogleGeocoder("secret-key", client=google_client(payload)).geocode("x")
    assert caught.value.fatal is fatal and "secret-key" not in str(caught.value)


def test_google_zero_results_is_an_empty_list_and_http_errors_never_leak_the_key():
    assert GoogleGeocoder("k", client=google_client({"status": "ZERO_RESULTS", "results": []})).geocode("x") == []
    with pytest.raises(GeocoderError) as caught:
        GoogleGeocoder("secret-key", client=google_client({}, status=500)).geocode("x")
    assert "secret-key" not in str(caught.value) and "secret-key" not in repr(caught.value.__cause__)


def test_geocoder_is_built_only_with_a_key_and_not_when_switched_off():
    assert build_geocoder(Settings(_env_file=None)) is None
    assert build_geocoder(Settings(_env_file=None, geocoder="google", google_maps_api_key="k")) is not None
    assert build_geocoder(Settings(_env_file=None, geocoder="geoapify", geoapify_api_key="k")) is not None
    assert build_geocoder(Settings(_env_file=None, google_maps_api_key="k")) is None  # default is geoapify: no key
    assert build_geocoder(Settings(_env_file=None, geoapify_api_key="k", geocoder="none")) is None


# --- runner --------------------------------------------------------------------------------------------


def runner(engine, provider, cfg):
    return LocationRunner(engine, provider, cfg, batch_size=10)


def test_runner_stores_a_resolved_position_and_audits_it(session, migrated_engine, cfg):
    incident = f.make_incident(session, location_text="Harare CBD", credibility_score=0.6)
    session.commit()
    summary = runner(migrated_engine, FakeProvider([result()]), cfg).run()

    assert (summary.attempted, summary.resolved) == (1, 1)
    session.expire_all()
    incident = session.get(Incident, incident.id)
    assert incident.location_status == "resolved" and incident.geom is not None
    assert incident.location_source == "Fake gazetteer" and incident.location_precision_m == 40.0
    assert incident.location_candidates[0]["label"] == "Harare CBD" and incident.location_updated_at
    assert incident.credibility_score == 0.6  # geography never changes credibility
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "incident.location_proposed"))
    assert event.actor_user_id is None and event.details["status"] == "resolved"


def test_runner_leaves_ambiguous_incidents_without_a_point(session, migrated_engine, cfg):
    incident = f.make_incident(session, location_text="Mbudzi")
    session.commit()
    provider = FakeProvider([result("Mbudzi, Harare"), result("Mbudzi, Mutare")])
    assert runner(migrated_engine, provider, cfg).run().ambiguous == 1
    session.expire_all()
    incident = session.get(Incident, incident.id)
    assert incident.location_status == "ambiguous" and incident.geom is None and len(incident.location_candidates) == 2


def test_runner_attempts_each_incident_once_and_never_overrides_editors(session, migrated_engine, cfg):
    editor = f.make_user(session, "editor")
    confirmed = f.make_incident(session, location_text="Harare", location_status="editor_confirmed",
                                geom=point(*HARARE), location_confirmed_by=editor.id)
    closed = f.make_incident(session, location_text="Bulawayo", status="rejected")
    fresh = f.make_incident(session, location_text="Harare CBD")
    session.commit()
    provider = FakeProvider([result()])

    assert runner(migrated_engine, provider, cfg).run().attempted == 1
    assert runner(migrated_engine, provider, cfg).run().attempted == 0
    assert provider.queries == ["Harare CBD"]
    session.expire_all()
    assert session.get(Incident, confirmed.id).location_status == "editor_confirmed"
    assert session.get(Incident, closed.id).location_updated_at is None


def test_provider_errors_leave_incidents_for_a_later_attempt(session, migrated_engine, cfg):
    incident = f.make_incident(session, location_text="Harare CBD")
    session.commit()
    summary = runner(migrated_engine, FakeProvider(error=GeocoderError("quota")), cfg).run()
    assert summary.provider_errors == 1 and summary.attempted == 0 and not summary.stopped_early
    session.expire_all()
    assert session.get(Incident, incident.id).location_updated_at is None

    fatal = runner(migrated_engine, FakeProvider(error=GeocoderError("denied", fatal=True)), cfg).run()
    assert fatal.stopped_early


def test_incidents_without_location_text_are_marked_attempted(session, migrated_engine, cfg):
    incident = f.make_incident(session, location_text=None)
    session.commit()
    provider = FakeProvider([result()])
    runner(migrated_engine, provider, cfg).run()
    session.expire_all()
    assert provider.queries == [] and session.get(Incident, incident.id).location_updated_at is not None


# --- blackspot matching ------------------------------------------------------------------------------------


def make_spot(session, metres_north, level="high", name="Spot"):
    spot = Blackspot(name=name, geom=offset_north(metres_north), source_name="Test dataset", risk_level=level)
    session.add(spot)
    session.flush()
    return spot


def located(session, location_status="editor_confirmed", precision=None, **kw):
    return f.make_incident(session, geom=point(*HARARE), location_status=location_status, location_precision_m=precision, **kw)


def test_matching_uses_the_500m_radius_boundary(session):
    near, far = make_spot(session, 400, name="Near"), make_spot(session, 620, name="Far")
    incident = located(session)
    found = recompute_matches(session, incident, 500)
    assert [lvl for lvl, _ in found] == ["high"]
    rows = session.scalars(select(IncidentBlackspotMatch)).all()
    assert [r.blackspot_id for r in rows] == [near.id] and 395 < rows[0].distance_meters < 405
    assert far.id not in [r.blackspot_id for r in rows]
    assert incident.geographic_risk_score == pytest.approx(0.75 * (1 - 0.5 * 0.8), abs=0.01)


def test_matching_is_replaced_not_duplicated_and_follows_the_radius(session):
    make_spot(session, 400)
    incident = located(session)
    recompute_matches(session, incident, 500)
    recompute_matches(session, incident, 500)
    assert len(session.scalars(select(IncidentBlackspotMatch)).all()) == 1
    recompute_matches(session, incident, 300)
    assert session.scalars(select(IncidentBlackspotMatch)).all() == [] and incident.geographic_risk_score is None


@pytest.mark.parametrize(
    "status, precision, matched",
    [("editor_confirmed", None, True), ("editor_confirmed", 200, True), ("editor_confirmed", 2000, False),
     ("resolved", 100, True), ("resolved", None, False), ("resolved", 1200, False), ("ambiguous", 10, False)],
)
def test_only_firm_positions_are_matched(session, status, precision, matched):
    make_spot(session, 100)
    incident = located(session, status, precision)
    assert bool(recompute_matches(session, incident, 500)) is matched


def test_matching_never_touches_credibility_and_raises_priority_once(session):
    make_spot(session, 10, level="critical")
    incident = located(session, credibility_score=0.4, review_priority="normal")
    recompute_matches(session, incident, 500)
    assert incident.credibility_score == 0.4 and incident.review_priority == "high"
    recompute_matches(session, incident, 500)  # again: no second bump
    assert incident.review_priority == "high"


def test_scoring_rules():
    assert scoring.geographic_risk([], 500) is None
    assert scoring.geographic_risk([("critical", 0)], 500) == 1.0
    assert scoring.geographic_risk([("low", 0), ("high", 500)], 500) == 0.375
    assert scoring.raise_priority("urgent", None, 1.0) == "urgent"
    assert scoring.raise_priority("low", 0.9, 0.95) == "low"


# --- API ------------------------------------------------------------------------------------------------------


def test_location_and_blackspot_match_endpoints(client, session):
    sign_in(client, session, "analyst")
    incident = located(session, "editor_confirmed", None, location_text="Samora Machel Ave")
    vague = f.make_incident(session, location_status="ambiguous")
    session.commit()

    assert client.get(f"{V1}/incidents/{incident.id}/blackspot-matches").json()["status"] == "unavailable"
    spot = make_spot(session, 250, "critical", "Samora corner")
    session.commit()
    assert client.get(f"{V1}/incidents/{incident.id}/blackspot-matches").json()["status"] == "no_match"
    recompute_matches(session, incident, 500)
    session.commit()

    body = client.get(f"{V1}/incidents/{incident.id}/blackspot-matches").json()
    assert body["status"] == "matched" and body["radius_meters"] == 500 and body["geographic_risk_score"] > 0.6
    match = body["matches"][0]
    assert match["blackspot"]["id"] == str(spot.id) and 245 < match["distance_meters"] < 255
    assert match["blackspot"]["geometry"]["type"] == "Point"
    assert client.get(f"{V1}/incidents/{vague.id}/blackspot-matches").json()["status"] == "location_unknown"

    location = client.get(f"{V1}/incidents/{incident.id}/location").json()
    assert location["status"] == "editor_confirmed" and location["confirmed_by_editor"] is True
    assert location["coordinates"]["latitude"] == pytest.approx(HARARE[0])
    assert client.get(f"{V1}/incidents/00000000-0000-0000-0000-000000000000/location").status_code == 404


def test_blackspot_endpoints_return_geojson_lng_lat(client, session):
    sign_in(client, session, "analyst")
    spot = make_spot(session, 0, "medium", "Alpha")
    make_spot(session, 100, "high", "Beta")
    session.commit()

    listing = client.get(f"{V1}/blackspots").json()
    assert listing["total"] == 2 and [i["name"] for i in listing["items"]] == ["Alpha", "Beta"]
    assert [i["name"] for i in client.get(f"{V1}/blackspots", params={"risk_level": "high"}).json()["items"]] == ["Beta"]
    detail = client.get(f"{V1}/blackspots/{spot.id}").json()
    assert detail["geometry"]["coordinates"] == [pytest.approx(HARARE[1]), pytest.approx(HARARE[0])]
    assert detail["source_name"] == "Test dataset" and detail["risk_level"] == "medium"
    assert client.get(f"{V1}/blackspots/00000000-0000-0000-0000-000000000000").status_code == 404


def test_map_draws_only_firm_positions_and_counts_the_rest(client, session):
    sign_in(client, session, "analyst")
    editor = f.make_user(session, "editor")
    candidate = located(session, "resolved", 40, location_text="A")
    confirmed = located(session, "editor_confirmed", None, location_text="B")
    approved = located(session, "editor_confirmed", None, location_text="C")
    f.make_review(session, approved, f.make_bulletin(session, approved, editor), editor)
    approved.status = "approved"
    located(session, "editor_confirmed", None, status="rejected")  # hidden
    f.make_incident(session, location_status="ambiguous")  # counted, not drawn
    f.make_incident(session)  # unresolved: counted, not drawn
    make_spot(session, 0)
    session.commit()

    body = client.get(f"{V1}/map").json()
    kinds = {m["id"]: m["marker_kind"] for m in body["incidents"]}
    assert kinds == {str(candidate.id): "candidate", str(confirmed.id): "editor_confirmed", str(approved.id): "approved"}
    assert body["unmapped_incident_count"] == 2 and len(body["blackspots"]) == 1
    assert body["generated_at"].endswith("Z")
    assert client.get(f"{V1}/map", params={"include_blackspots": "false"}).json()["blackspots"] == []


# --- import script --------------------------------------------------------------------------------------------


def test_import_requires_a_cited_source_and_zimbabwean_coordinates():
    header = "name,latitude,longitude,risk_level,source_name,period_start\n"
    ok, errors = parse_rows(io.StringIO(header + "Spot A,-17.8,31.0,HIGH,ZRP 2023 report,2023-01-01\n"))
    assert errors == [] and ok[0].risk_level == "high" and ok[0].source_name == "ZRP 2023 report"

    _, errors = parse_rows(io.StringIO(header + "Spot B,-17.8,31.0,high,,\n"))
    assert "source_name is required" in errors[0]
    _, errors = parse_rows(io.StringIO(header + "Spot C,31.0,-17.8,high,ZRP,\n"))
    assert "outside Zimbabwe" in errors[0]
    _, errors = parse_rows(io.StringIO(header + "Spot D,-17.8,31.0,severe,ZRP,\n"))
    assert errors
    _, errors = parse_rows(io.StringIO("name,latitude\nx,1\n"))
    assert "missing column" in errors[0]
