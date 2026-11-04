"""The public data boundary: only approved AND published bulletins are ever visible."""

import pytest
from geoalchemy2 import WKTElement

import db_factories as f
from app.models import Blackspot
from public_helpers import configure, make_published_alert  # noqa: F401

pytestmark = pytest.mark.usefixtures("migrated_engine")

P = "/api/v1/public"
INTERNAL_KEYS = {
    "credibility_score", "geographic_risk_score", "review_priority", "notes", "reviewer_id",
    "created_by", "extraction_output", "location_candidates", "location_note", "incident_id",
    "approval_review_id", "bulletin_version_id", "reference_code",
}


def _all_keys(value, found=None):
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            _all_keys(v, found)
    elif isinstance(value, list):
        for v in value:
            _all_keys(v, found)
    return found


def _hidden_records(session):
    """Records that must never be public, in every non-published shape."""
    editor = f.make_user(session, "editor")
    # 1. candidate incident with a draft bulletin
    cand = f.make_incident(session, status="candidate", location_text="Candidate road")
    f.make_bulletin(session, cand, editor)
    # 2. approved but NOT published (alert row is only 'ready')
    approved = f.make_incident(session, status="under_review", location_text="Approved only")
    b = f.make_bulletin(session, approved, editor)
    r = f.make_review(session, approved, b, editor)
    approved.status = "approved"
    session.flush()
    f.make_alert(session, approved, b, r)  # status defaults to 'ready'
    # 3. rejected
    rejected = f.make_incident(session, status="under_review")
    b2 = f.make_bulletin(session, rejected, editor)
    f.make_review(session, rejected, b2, editor, decision="rejected")
    rejected.status = "rejected"
    session.flush()
    session.commit()
    return [cand, approved, rejected]


def test_published_alerts_are_returned(client, session, configure):
    alert, _, bulletin = make_published_alert(session)
    body = client.get(f"{P}/alerts").json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(alert.id) and item["headline"] == bulletin.headline
    assert item["province"] == "Mashonaland East" and item["has_map_location"] is True
    assert item["sources"] and "name" in item["sources"][0]


def test_unpublished_states_never_appear_anywhere(client, session, configure):
    hidden = _hidden_records(session)
    withdrawn, inc, _ = make_published_alert(session, headline="[SYNTHETIC] Withdrawn one")
    withdrawn.status = "withdrawn"
    inc.status = "approved"
    session.commit()
    visible, _, _ = make_published_alert(session, headline="[SYNTHETIC] Visible one")

    listing = client.get(f"{P}/alerts").json()
    assert [i["id"] for i in listing["items"]] == [str(visible.id)]
    assert client.get(f"{P}/alerts/{withdrawn.id}").status_code == 404
    assert client.get(f"{P}/summary").json()["recent_alert_count"] == 1
    features = client.get(f"{P}/map").json()["features"]
    assert [x["id"] for x in features] == [str(visible.id)]
    text = client.get(f"{P}/alerts").text + client.get(f"{P}/map").text
    for incident in hidden:
        assert str(incident.id) not in text and incident.reference_code not in text


def test_responses_expose_no_internal_fields(client, session, configure):
    alert, _, _ = make_published_alert(session)
    for url in (f"{P}/alerts", f"{P}/alerts/{alert.id}", f"{P}/map", f"{P}/summary"):
        keys = _all_keys(client.get(url).json())
        assert not (keys & INTERNAL_KEYS), (url, keys & INTERNAL_KEYS)


def test_pagination_search_and_filters(client, session, configure):
    for i in range(3):
        make_published_alert(session, headline=f"[SYNTHETIC] Crash number {i}")
    make_published_alert(
        session, headline="[SYNTHETIC] Pothole warning", incident_type="road_hazard",
        province="Harare", road_name="Samora Machel Avenue",
    )
    page = client.get(f"{P}/alerts", params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 4 and len(page["items"]) == 2
    assert client.get(f"{P}/alerts", params={"q": "pothole"}).json()["total"] == 1
    assert client.get(f"{P}/alerts", params={"province": "harare"}).json()["total"] == 1
    assert client.get(f"{P}/alerts", params={"road": "samora"}).json()["total"] == 1
    assert client.get(f"{P}/alerts", params={"hazard_type": "road_hazard"}).json()["total"] == 1
    assert client.get(f"{P}/alerts", params={"page_size": 1000}).status_code == 422
    assert client.get(f"{P}/alerts", params={"province": "Atlantis"}).status_code == 422
    first = client.get(f"{P}/alerts").json()["items"]
    assert first == client.get(f"{P}/alerts").json()["items"]  # stable ordering


def test_map_is_valid_geojson_and_withholds_unreliable_locations(client, session, configure):
    ok, _, _ = make_published_alert(session)
    make_published_alert(session, lat=None, lng=None, location_status="unresolved", headline="[SYNTHETIC] No position")
    make_published_alert(
        session, lat=-18.0, lng=31.0, location_status="ambiguous", headline="[SYNTHETIC] Ambiguous place"
    )
    data = client.get(f"{P}/map").json()
    assert data["type"] == "FeatureCollection" and len(data["features"]) == 1
    feature = data["features"][0]
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Point"
    lng, lat = feature["geometry"]["coordinates"]
    assert 25 < lng < 34 and -23 < lat < -15
    props = feature["properties"]
    assert props["status"] == "published" and props["alert_url"] == f"/public/alerts/{ok.id}"
    assert props["location_precision"] in {"exact", "approximate"}
    assert data["unlocated_count"] == 2
    detail = client.get(f"{P}/alerts/{ok.id}").json()
    assert detail["point"]["precision"] == "exact" and "conditions may have changed" in detail["notice"].lower()


def test_blackspots_are_only_sourced_history(client, session, configure):
    session.add(
        Blackspot(
            name="[SYNTHETIC] Test blackspot", geom=WKTElement("POINT(31.0 -17.8)", srid=4326),
            source_name="Synthetic test dataset", risk_level="high",
        )
    )
    session.commit()
    data = client.get(f"{P}/blackspots").json()
    assert data["total"] == 1 and data["items"][0]["source_name"] == "Synthetic test dataset"
    assert "not current alerts" in data["notice"]


def test_public_reads_are_rate_limited_and_cacheable(client, session, configure):
    configure(public_rate_limit_per_minute=2)
    assert client.get(f"{P}/alerts").headers["cache-control"].startswith("public")
    client.get(f"{P}/alerts")
    assert client.get(f"{P}/alerts").status_code == 429
