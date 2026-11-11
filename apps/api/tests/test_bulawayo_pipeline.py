"""Bulawayo / NUST scope against PostgreSQL: place gate in the pipeline, city news records, constraints.

The AI and article fetching are fakes, so nothing touches the network or costs money. All text is synthetic.
"""

import pytest
from sqlalchemy import func, select

import db_factories as f
from app.models import Incident, PublicAlert, SourceItem
from app.models.intelligence import IntelligenceRecord
from app.schemas.intelligence import IntelligenceExtraction
from intel_helpers import blank_details, intel_reply
from public_helpers import configure  # noqa: F401  (fixture)
from test_article_pipeline import FakeFetch, add_item, runner, status
from test_intelligence_pipeline import IntelExtractor, base_record, records

pytestmark = pytest.mark.usefixtures("migrated_engine")

REGION = dict(region="bulawayo", trusted_sources=frozenset({"Bulawayo24"}))


def city_reply(**overrides):
    base = dict(
        primary_category="city_news", primary_subtype="nust_news", record_kind="informational_development",
        temporal_status="unknown", geographic_scope="town", short_headline="NUST holds its graduation ceremony",
        neutral_summary="The National University of Science and Technology held its graduation ceremony.",
        event_or_announcement_date="2026-11-02", location_description="NUST campus, Bulawayo",
        province_or_region="Bulawayo", district_or_town="Bulawayo", road_name=None, nearest_landmark=None,
        source_attribution="NUST", evidence_references=["graduation ceremony"],
        details=blank_details(city_news={
            "organisation": "NUST", "topic": "graduation", "affected_area": None, "event_date": "2026-11-02"}),
    )
    base.update(overrides)
    return intel_reply(**base)


def run_region(session, engine, title, excerpt, reply, *, source_name=None):
    source = f.make_source(session)
    if source_name:
        source.name = source_name
        session.commit()
    item = add_item(session, source, title=title, excerpt=excerpt)
    extractor = IntelExtractor(reply)
    summary = runner(engine, FakeFetch(), extractor, **REGION).run()
    session.expire_all()
    return item, summary, extractor


# ---- the place gate in the pipeline ---------------------------------------------------------------------


def test_a_harare_item_is_filtered_before_any_fetch_or_ai_call(session, migrated_engine):
    item, summary, extractor = run_region(
        session, migrated_engine, "Kombi overturns along Seke Road", "Five people injured in Harare.", intel_reply())
    assert status(session, item) == "filtered" and "region" in item.screen_reason
    assert extractor.calls == [] and summary.filtered == 1


def test_a_nust_story_is_classified_as_city_news_and_never_becomes_an_incident(session, migrated_engine):
    item, summary, extractor = run_region(
        session, migrated_engine, "NUST graduation ceremony held",
        "Hundreds of students graduated at the National University of Science and Technology.", city_reply())
    record = records(session)[0]
    assert (record.primary_category, record.primary_subtype, record.record_kind) == (
        "city_news", "nust_news", "informational_development")
    assert record.incident_id is None and record.status == "candidate"  # a person still has to review it
    assert session.scalar(select(func.count()).select_from(Incident)) == 0
    assert session.scalar(select(func.count()).select_from(PublicAlert)) == 0
    assert (summary.intelligence_records, summary.incidents_created) == (1, 0)
    assert status(session, item) == "processed" and len(extractor.calls) == 1


def test_a_bulawayo_road_crash_is_still_an_incident_candidate(session, migrated_engine):
    _, summary, _ = run_region(
        session, migrated_engine, "Kombi overturns on Plumtree Road", "Five injured near Bulawayo.",
        intel_reply(road_name="Plumtree Road", district_or_town="Bulawayo", province_or_region="Matabeleland South"))
    assert summary.incidents_created == 1
    assert records(session)[0].primary_category == "road_incident"


def test_a_trusted_outlet_item_with_no_place_passes_but_the_same_item_from_a_national_feed_does_not(session, migrated_engine):
    title, excerpt = "Council approves water tariff", "Councillors debated the budget."
    trusted, _, _ = run_region(session, migrated_engine, title, excerpt, city_reply(
        primary_subtype="city_council", short_headline="Council approves water tariff"), source_name="Bulawayo24")
    other, _, extractor = run_region(session, migrated_engine, title + " again", excerpt, city_reply(), source_name="National Daily")
    assert status(session, trusted) == "processed"
    assert status(session, other) == "filtered" and len(extractor.calls) == 0


def test_without_a_region_the_pipeline_behaves_as_before(session, migrated_engine):
    item = add_item(session, title="Kombi overturns along Seke Road", excerpt="Five people injured in Harare.")
    extractor = IntelExtractor(intel_reply())
    summary = runner(migrated_engine, FakeFetch(), extractor).run()
    session.expire_all()
    assert status(session, item) == "processed" and summary.incidents_created == 1


# ---- schema and constraints ------------------------------------------------------------------------------


def test_city_news_can_never_be_an_actionable_event():
    intel = IntelligenceExtraction.model_validate(city_reply(record_kind="actionable_event"))
    assert intel.record_kind.value == "informational_development"
    assert "kind_adjusted" in [f.value for f in intel.data_quality_flags]
    assert intel.creates_incident is False


def test_replies_without_the_city_news_block_still_validate():
    reply = intel_reply()
    reply["details"].pop("city_news", None)
    assert IntelligenceExtraction.model_validate(reply).primary_category.value == "road_incident"


def test_the_database_accepts_city_news_and_rejects_mismatched_subtypes(session, db_error):
    record = base_record(session, primary_category="city_news", primary_subtype="nust_news",
                         record_kind="informational_development", geographic_scope="town")
    assert record.primary_category == "city_news"
    with db_error(session, "23514"):  # CHECK violation: a transport subtype under city_news
        record.primary_subtype = "road_closure"
        session.flush()


def test_the_database_still_refuses_a_city_news_record_linked_to_an_incident(session, db_error):
    incident = f.make_incident(session)
    record = base_record(session, primary_category="city_news", primary_subtype="nust_news",
                         record_kind="informational_development", geographic_scope="town")
    with db_error(session, "23514"):
        record.incident_id = incident.id
        session.flush()


# ---- subscriptions ---------------------------------------------------------------------------------------


def test_subscription_options_list_only_the_regions_provinces(client, configure):
    configure(subscription_provinces="Bulawayo,Matabeleland North,Matabeleland South")
    body = client.get("/api/v1/public/subscriptions/options").json()
    assert body["provinces"] == ["Bulawayo", "Matabeleland North", "Matabeleland South"]


def test_subscription_options_default_to_all_ten_provinces(client, configure):
    configure()
    assert len(client.get("/api/v1/public/subscriptions/options").json()["provinces"]) == 10
