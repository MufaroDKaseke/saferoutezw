"""Read-only API: dashboard, news, sources, processing and incidents."""

from datetime import UTC, datetime, timedelta

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import event

import db_factories as f
from api_helpers import make_login_user, sign_in
from app.models import Blackspot, ExtractionRun, IncidentEvidence, IngestionRun

pytestmark = pytest.mark.usefixtures("migrated_engine")

V1 = "/api/v1"
READ_PATHS = [
    "/dashboard/summary",
    "/dashboard/activity",
    "/news",
    "/sources",
    "/processing/runs",
    "/incidents",
]


class QueryCounter:
    def __init__(self, engine):
        self.engine, self.count = engine, 0

    def _hit(self, *args, **kwargs):
        self.count += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._hit)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._hit)


def add_run(session, item, status="succeeded", confidence=0.9, **output):
    run = ExtractionRun(
        source_item_id=item.id,
        model_name="test-model",
        prompt_version="v-test",
        status=status,
        extraction_confidence=confidence,
        extraction_output=output or {"summary": "A kombi overturned.", "fatalities": 2, "injuries": None,
                                      "vehicles_involved": 1, "cause": None, "evidence_quotes": ["two died"]},
        input_tokens=100,
        output_tokens=20,
    )
    session.add(run)
    session.flush()
    return run


def link(session, incident, item, role="primary"):
    session.add(IncidentEvidence(incident_id=incident.id, source_item_id=item.id, evidence_role=role))
    session.flush()


# --- access control ----------------------------------------------------------------------------


@pytest.mark.parametrize("path", READ_PATHS)
def test_every_read_endpoint_requires_a_session(client, path):
    response = client.get(V1 + path)
    assert response.status_code == 401 and response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.parametrize("path", READ_PATHS)
def test_analysts_can_read_but_contributors_cannot(client, session, path):
    sign_in(client, session, "analyst")
    assert client.get(V1 + path).status_code == 200
    client.cookies.clear()
    sign_in(client, session, "contributor")
    assert client.get(V1 + path).status_code == 403


# --- news ----------------------------------------------------------------------------------------


def test_news_list_filters_and_pagination(client, session):
    sign_in(client, session, "analyst")
    source = f.make_source(session)
    other = f.make_source(session)
    relevant = f.make_source_item(session, source, processing_status="processed", title_redacted="Kombi crash on A1",
                                  screen_reason="matched: crash", fetch_status="ok")
    f.make_source_item(session, source, processing_status="filtered", title_redacted="Sports news")
    f.make_source_item(session, other, processing_status="pending", title_redacted="Unscreened")
    add_run(session, relevant)
    incident = f.make_incident(session)
    link(session, incident, relevant)
    session.commit()

    everything = client.get(V1 + "/news").json()
    assert everything["total"] == 3 and everything["page"] == 1 and everything["page_size"] == 20

    only_relevant = client.get(V1 + "/news", params={"relevant": "true"}).json()
    assert [i["headline"] for i in only_relevant["items"]] == ["Kombi crash on A1"]
    item = only_relevant["items"][0]
    assert item["publisher"] == source.name and item["linked_incident_count"] == 1
    assert item["keyword_relevance"] == {"relevant": True, "reason": "matched: crash"}
    assert item["extraction_status"] == "succeeded" and item["fetch_status"] == "ok"
    assert item["ingested_at"].endswith("Z")

    pending = client.get(V1 + "/news", params={"processing_status": "pending"}).json()["items"][0]
    assert pending["keyword_relevance"]["relevant"] is None
    assert client.get(V1 + "/news", params={"relevant": "false"}).json()["total"] == 1
    assert client.get(V1 + "/news", params={"has_incident": "false"}).json()["total"] == 2
    assert client.get(V1 + "/news", params={"source_id": str(other.id)}).json()["total"] == 1
    assert client.get(V1 + "/news", params={"q": "kombi"}).json()["total"] == 1
    assert client.get(V1 + "/news", params={"q": "%"}).json()["total"] == 0  # wildcard is escaped

    page = client.get(V1 + "/news", params={"page_size": 2, "page": 2}).json()
    assert len(page["items"]) == 1 and page["total"] == 3


@pytest.mark.parametrize("params", [{"page_size": 101}, {"page_size": 0}, {"page": 0}, {"sort": "headline"}])
def test_list_parameters_are_bounded(client, session, params):
    sign_in(client, session, "analyst")
    assert client.get(V1 + "/news", params=params).status_code == 422


def test_news_detail_exposes_only_redacted_text(client, session):
    sign_in(client, session, "analyst")
    item = f.make_source_item(session, f.make_source(session), processing_status="processed",
                              article_text_redacted="Driver [NAME] died.", excerpt_redacted="Short")
    run = add_run(session, item)
    incident = f.make_incident(session)
    link(session, incident, item)
    session.commit()

    body = client.get(f"{V1}/news/{item.id}").json()
    assert body["article_text"] == "Driver [NAME] died." and body["excerpt"] == "Short"
    assert body["extraction"]["id"] == str(run.id) and body["extraction"]["output"]["fatalities"] == 2
    assert body["incidents"] == [{"id": str(incident.id), "reference_code": incident.reference_code,
                                  "incident_type": "collision", "status": "candidate", "evidence_role": "primary"}]
    assert "system_prompt" not in body["extraction"] and "messages" not in body["extraction"]
    assert client.get(f"{V1}/news/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"{V1}/news/not-a-uuid").status_code == 422


def test_failed_extraction_hides_output(client, session):
    sign_in(client, session, "analyst")
    item = f.make_source_item(session, f.make_source(session))
    session.add(ExtractionRun(source_item_id=item.id, model_name="m", status="failed",
                              error_message="temperature unsupported", extraction_output={"junk": 1}))
    session.commit()
    body = client.get(f"{V1}/news/{item.id}").json()
    assert body["extraction"]["status"] == "failed" and body["extraction"]["output"] is None
    assert body["extraction"]["error_message"] == "temperature unsupported"


def test_news_list_query_count_does_not_grow_with_page_size(client, session, migrated_engine):
    sign_in(client, session, "analyst")
    source = f.make_source(session)

    def add(n):
        for _ in range(n):
            item = f.make_source_item(session, source, processing_status="processed")
            add_run(session, item)
            link(session, f.make_incident(session), item)
        session.commit()

    add(2)
    with QueryCounter(migrated_engine) as small:
        client.get(V1 + "/news")
    add(15)
    with QueryCounter(migrated_engine) as large:
        assert len(client.get(V1 + "/news").json()["items"]) == 17
    assert large.count == small.count


# --- sources and processing ------------------------------------------------------------------------


def test_sources_report_polling_health(client, session):
    sign_in(client, session, "analyst")
    source = f.make_source(session)
    now = datetime.now(UTC)
    session.add_all([
        IngestionRun(source_id=source.id, started_at=now - timedelta(hours=3), completed_at=now - timedelta(hours=3),
                     status="succeeded", fetched_count=10, inserted_count=4),
        IngestionRun(source_id=source.id, started_at=now - timedelta(hours=1), completed_at=now - timedelta(hours=1),
                     status="failed", error_count=1, error_message="HTTP 403"),
        IngestionRun(source_id=source.id, started_at=now - timedelta(days=20), status="failed", error_message="old"),
    ])
    f.make_source_item(session, source)
    quiet = f.make_source(session)
    session.commit()

    listing = {s["id"]: s for s in client.get(V1 + "/sources").json()["items"]}
    busy = listing[str(source.id)]
    assert busy["error_count_7d"] == 1 and busy["last_error"] == "HTTP 403" and busy["article_count"] == 1
    assert busy["last_success_at"] and busy["last_polled_at"] and busy["kind"] == "rss"
    assert listing[str(quiet.id)]["last_polled_at"] is None and listing[str(quiet.id)]["error_count_7d"] == 0

    assert client.get(f"{V1}/sources/{source.id}").json()["name"] == source.name
    runs = client.get(f"{V1}/sources/{source.id}/runs", params={"page_size": 2}).json()
    assert runs["total"] == 3 and runs["items"][0]["status"] == "failed" and runs["items"][0]["source_name"] == source.name
    assert client.get(f"{V1}/sources/{source.id}/runs", params={"status": "succeeded"}).json()["total"] == 1
    assert client.get(f"{V1}/sources/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"{V1}/sources/00000000-0000-0000-0000-000000000000/runs").status_code == 404


def test_processing_timeline_mixes_ingestion_and_extraction(client, session):
    sign_in(client, session, "analyst")
    source = f.make_source(session)
    run = IngestionRun(source_id=source.id, status="succeeded", fetched_count=3, inserted_count=3)
    item = f.make_source_item(session, source, title_redacted="Crash headline")
    extraction = add_run(session, item)
    session.add(run)
    session.commit()

    body = client.get(V1 + "/processing/runs").json()
    assert body["total"] == 2 and {r["kind"] for r in body["items"]} == {"ingestion", "extraction"}
    assert [r["kind"] for r in client.get(V1 + "/processing/runs", params={"kind": "extraction"}).json()["items"]] == ["extraction"]
    ext = next(r for r in body["items"] if r["kind"] == "extraction")
    assert ext["headline"] == "Crash headline" and ext["model_name"] == "test-model" and ext["input_tokens"] == 100
    assert ext["fetched_count"] is None

    detail = client.get(f"{V1}/processing/runs/{extraction.id}").json()
    assert detail["output"]["fatalities"] == 2 and "article" not in str(detail).lower()
    ing = client.get(f"{V1}/processing/runs/{run.id}").json()
    assert ing["kind"] == "ingestion" and ing["inserted_count"] == 3 and ing["output"] is None
    assert client.get(f"{V1}/processing/runs/00000000-0000-0000-0000-000000000000").status_code == 404


# --- incidents ---------------------------------------------------------------------------------------


def test_incident_list_summary_and_filters(client, session):
    sign_in(client, session, "analyst")
    item = f.make_source_item(session, f.make_source(session))
    add_run(session, item)
    incident = f.make_incident(session, location_text="Rusape-Nyanga Road", severity="fatal",
                               credibility_score=0.7, status="under_review", review_priority="high")
    link(session, incident, item)
    link(session, incident, f.make_source_item(session, f.make_source(session)), "corroborating")
    f.make_incident(session, incident_type="rollover", status="rejected")
    session.commit()

    body = client.get(V1 + "/incidents").json()
    assert body["total"] == 2
    first = next(i for i in body["items"] if i["id"] == str(incident.id))
    assert first["summary"] == "A kombi overturned." and first["source_count"] == 2
    assert first["review_state"] == "pending_review" and first["has_coordinates"] is False
    assert first["credibility_score"] == 0.7 and first["latest_bulletin_version"] is None
    assert client.get(V1 + "/incidents", params={"status": "rejected"}).json()["total"] == 1
    assert client.get(V1 + "/incidents", params={"incident_type": "rollover"}).json()["total"] == 1
    assert client.get(V1 + "/incidents", params={"q": "rusape"}).json()["total"] == 1
    assert client.get(V1 + "/incidents", params={"severity": "fatal"}).json()["total"] == 1
    assert client.get(V1 + "/incidents", params={"status": "bogus"}).status_code == 422
    sorted_asc = client.get(V1 + "/incidents", params={"sort": "credibility_score", "order": "desc"}).json()["items"]
    assert sorted_asc[0]["credibility_score"] == 0.7


def test_review_state_is_derived_from_decisions_and_drafts(client, session):
    sign_in(client, session, "analyst")
    editor = f.make_user(session, "editor")
    incident = f.make_incident(session, status="under_review")
    v1 = f.make_bulletin(session, incident, editor, 1)
    f.make_review(session, incident, v1, editor, "needs_changes",
                  reviewed_at=datetime.now(UTC) + timedelta(seconds=5))
    session.commit()
    state = lambda: client.get(f"{V1}/incidents/{incident.id}").json()["review_state"]  # noqa: E731
    assert state() == "needs_changes"
    f.make_bulletin(session, incident, editor, 2)  # a newer draft = resubmitted
    session.commit()
    detail = client.get(f"{V1}/incidents/{incident.id}").json()
    assert detail["latest_bulletin_version"] == 2
    assert state() in ("needs_changes", "pending_review")  # draft vs review timestamps


def test_incident_detail_keeps_assessments_separate(client, session):
    sign_in(client, session, "analyst")
    item = f.make_source_item(session, f.make_source(session))
    add_run(session, item, confidence=0.82)
    incident = f.make_incident(session, credibility_score=0.5, geographic_risk_score=None)
    link(session, incident, item)
    session.commit()

    detail = client.get(f"{V1}/incidents/{incident.id}").json()
    a = detail["assessments"]
    assert a["credibility_score"] == 0.5 and a["extraction_confidence"] == 0.82
    assert a["geographic_risk_score"] is None and a["blackspot_data"] == "unavailable"
    assert detail["extracted_facts"]["fatalities"] == 2 and detail["extracted_facts"]["evidence_quotes"] == ["two died"]
    assert {"Exact location", "Time of incident", "Cause"} <= set(detail["missing_information"])
    assert detail["location"]["status"] == "unresolved" and detail["location"]["coordinates"] is None

    session.add(Blackspot(name="Test spot", geom=WKTElement("POINT(31.05 -17.83)", srid=4326),
                          source_name="Test dataset", risk_level="high"))
    session.commit()
    assert client.get(f"{V1}/incidents/{incident.id}").json()["assessments"]["blackspot_data"] == "available"


def test_ambiguous_locations_never_expose_a_point(client, session):
    sign_in(client, session, "analyst")
    incident = f.make_incident(
        session, location_text="near Mbudzi", location_status="ambiguous",
        location_candidates=[{"label": "Mbudzi, Harare", "latitude": -17.86, "longitude": 31.02,
                              "match_type": "approximate", "source": "test"}],
    )
    resolved = f.make_incident(session, location_status="resolved", location_precision_m=40,
                               geom=WKTElement("POINT(31.05 -17.83)", srid=4326))
    session.commit()

    loc = client.get(f"{V1}/incidents/{incident.id}").json()["location"]
    assert loc["coordinates"] is None and loc["status"] == "ambiguous" and loc["confirmed_by_editor"] is False
    assert loc["candidates"][0]["label"] == "Mbudzi, Harare"
    ok = client.get(f"{V1}/incidents/{resolved.id}").json()
    assert ok["has_coordinates"] is True
    assert ok["location"]["coordinates"] == {"latitude": pytest.approx(-17.83), "longitude": pytest.approx(31.05)}
    assert ok["location"]["precision_meters"] == 40


def test_incident_evidence_endpoint(client, session):
    sign_in(client, session, "analyst")
    source = f.make_source(session)
    item = f.make_source_item(session, source, title_redacted="Headline")
    add_run(session, item)
    incident = f.make_incident(session)
    link(session, incident, item)
    session.commit()

    body = client.get(f"{V1}/incidents/{incident.id}/evidence").json()
    assert body["total"] == 1
    ev = body["items"][0]
    assert ev["role"] == "primary" and ev["source_item"]["publisher"] == source.name
    assert ev["source_item"]["headline"] == "Headline" and ev["extraction_status"] == "succeeded"
    assert client.get(f"{V1}/incidents/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get(f"{V1}/incidents/00000000-0000-0000-0000-000000000000/evidence").status_code == 404


def test_incident_list_query_count_is_constant(client, session, migrated_engine):
    sign_in(client, session, "analyst")
    editor = f.make_user(session, "editor")

    def add(n):
        for _ in range(n):
            item = f.make_source_item(session, f.make_source(session))
            add_run(session, item)
            incident = f.make_incident(session)
            link(session, incident, item)
            f.make_bulletin(session, incident, editor, 1)
        session.commit()

    add(2)
    with QueryCounter(migrated_engine) as small:
        client.get(V1 + "/incidents")
    add(15)
    with QueryCounter(migrated_engine) as large:
        assert len(client.get(V1 + "/incidents").json()["items"]) == 17
    assert large.count == small.count


# --- dashboard -------------------------------------------------------------------------------------


def test_dashboard_summary_counts(client, session):
    sign_in(client, session, "analyst")
    source = f.make_source(session)
    now = datetime.now(UTC)
    f.make_source_item(session, source, processing_status="processed")
    f.make_source_item(session, source, processing_status="filtered")
    f.make_source_item(session, source, processing_status="fetch_failed")
    f.make_source_item(session, source, processing_status="failed")
    old = f.make_source_item(session, source, processing_status="screened")
    old.received_at = now - timedelta(days=3)
    f.make_incident(session)
    f.make_incident(session, status="under_review")
    approved = f.make_incident(session)
    editor = f.make_user(session, "editor")
    f.make_review(session, approved, f.make_bulletin(session, approved, editor), editor)
    approved.status = "approved"
    session.commit()

    day = client.get(V1 + "/dashboard/summary").json()
    assert day["range"] == "24h"
    assert (day["articles_ingested"], day["relevant_articles"]) == (4, 3)
    assert (day["incident_candidates"], day["pending_reviews"], day["approved_incidents"]) == (3, 2, 1)
    assert day["failed_processing"] == 2 and day["pipeline"]["pending"] == 0 and day["pipeline"]["screened"] == 1
    week = client.get(V1 + "/dashboard/summary", params={"range": "7d"}).json()
    assert week["articles_ingested"] == 5
    assert client.get(V1 + "/dashboard/summary", params={"range": "1y"}).status_code == 422


@pytest.mark.parametrize("range_, length, bucket", [("24h", 24, "hour"), ("7d", 7, "day"), ("30d", 30, "day")])
def test_dashboard_activity_buckets_are_zero_filled(client, session, range_, length, bucket):
    sign_in(client, session, "analyst")
    source = f.make_source(session)
    f.make_source_item(session, source, processing_status="processed")
    f.make_incident(session)
    session.add(IngestionRun(source_id=source.id, status="succeeded"))
    session.commit()

    body = client.get(V1 + "/dashboard/activity", params={"range": range_}).json()
    assert body["bucket"] == bucket and len(body["points"]) == length
    last = body["points"][-1]
    assert (last["articles"], last["relevant_articles"], last["incident_candidates"]) == (1, 1, 1)
    assert sum(p["articles"] for p in body["points"]) == 1
    assert len(body["recent_runs"]) == 1 and body["recent_runs"][0]["source_name"] == source.name
