"""Transport intelligence against PostgreSQL: the seven acceptance scenarios and integrity rules.

Fetching and the AI are replaced by fakes, so nothing touches the network or costs money.
All text is synthetic.
"""

import pytest
from sqlalchemy import func, select

import db_factories as f
from app.models import AuditEvent, Incident, PublicAlert, SourceItem
from app.models.intelligence import (
    IntelligenceRecord,
    IntelligenceReview,
    IntelligenceVersion,
    PublicationOutput,
    StatisticalObservation,
)
from app.schemas.intelligence import IntelligenceExtraction
from app.services.extraction import ExtractionOutput
from intel_helpers import (
    closure_reply,
    infrastructure_reply,
    intel_reply,
    policy_reply,
    stat,
    statistics_reply,
)
from test_article_pipeline import FakeFetch, add_item, runner, status

pytestmark = pytest.mark.usefixtures("migrated_engine")


class IntelExtractor:
    """Stands in for the OpenAI extractor, returning prepared unified replies."""

    model_name = "fake-model"

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def extract(self, item):
        self.calls.append(item)
        intel = IntelligenceExtraction.model_validate(self.replies.pop(0))
        return ExtractionOutput(
            intel.to_legacy_result(), "fake-model-1", "transport-intel-v1", 100, 20, intelligence=intel
        )


def process(session, engine, title, excerpt, reply):
    item = add_item(session, title=title, excerpt=excerpt)
    extractor = IntelExtractor(reply)
    summary = runner(engine, FakeFetch(), extractor).run()
    session.expire_all()
    return item, summary, extractor


def records(session):
    return session.scalars(select(IntelligenceRecord)).all()


# --- scenario 1: road accident -------------------------------------------------------------


def test_scenario_1_accident_becomes_an_incident_candidate_plus_a_linked_record(session, migrated_engine):
    item, summary, _ = process(session, migrated_engine, "Kombi collides with truck near Harare",
                               "Five killed in a collision.", intel_reply(geographic_scope="approximate_point"))
    incident = session.scalars(select(Incident)).one()
    record = records(session)[0]
    assert incident.status == "candidate"  # review required; not published
    assert incident.geom is None  # location is resolved later and may stay uncertain
    assert (record.primary_category, record.record_kind, record.status) == ("road_incident", "actionable_event", "candidate")
    assert record.incident_id == incident.id and record.geographic_scope == "approximate_point"
    assert status(session, item) == "processed" and summary.incidents_created == 1
    assert session.scalar(select(func.count()).select_from(PublicAlert)) == 0  # nothing public yet
    assert session.scalars(select(AuditEvent).where(AuditEvent.action == "intelligence.candidate_created")).one()


# --- scenario 2: traffic disruption --------------------------------------------------------


def test_scenario_2_closure_is_an_actionable_event_with_a_road_closure_incident(session, migrated_engine):
    _, summary, _ = process(session, migrated_engine, "Road closed at Beitbridge for bridge repairs",
                            "The access road will be closed from Thursday.", closure_reply())
    incident = session.scalars(select(Incident)).one()
    record = records(session)[0]
    assert incident.incident_type == "road_closure" and incident.status == "candidate"
    assert record.primary_category == "traffic_disruption" and record.temporal_status == "planned"
    assert record.details["affected_road"] == "Beitbridge access road" and record.incident_id == incident.id
    assert summary.incidents_created == 1


# --- scenario 3: infrastructure -------------------------------------------------------------


def test_scenario_3_infrastructure_is_a_record_only_and_never_a_closure(session, migrated_engine):
    _, summary, _ = process(session, migrated_engine, "ZINARA announces road rehabilitation",
                            "The Harare-Bulawayo road will be rehabilitated.", infrastructure_reply())
    record = records(session)[0]
    assert (record.primary_category, record.record_kind) == ("road_infrastructure", "informational_development")
    assert record.incident_id is None and record.topic_key.startswith("road_infrastructure:")
    assert session.scalar(select(func.count()).select_from(Incident)) == 0
    assert (summary.intelligence_records, summary.incidents_created) == (1, 0)


# --- scenario 4: statistics ----------------------------------------------------------------


def test_scenario_4_statistics_keep_structured_metrics_and_create_no_incidents(session, migrated_engine):
    reply = statistics_reply(statistics=[
        stat("road deaths", 1800), stat("road injuries", 9000, "persons", is_preliminary=True),
    ])
    process(session, migrated_engine, "ZRP releases annual road accident statistics",
            "Road deaths in 2025.", reply)
    assert session.scalar(select(func.count()).select_from(Incident)) == 0
    record = records(session)[0]
    assert record.geographic_scope == "national" and record.record_kind == "statistical_report"
    rows = session.scalars(select(StatisticalObservation).order_by(StatisticalObservation.metric)).all()
    assert [(r.metric, float(r.value), r.unit) for r in rows] == [
        ("road deaths", 1800.0, "persons"), ("road injuries", 9000.0, "persons"),
    ]
    first = rows[0]
    assert (first.period_start.isoformat(), first.period_end.isoformat()) == ("2025-01-01", "2025-12-31")
    assert first.source_reference == "Zimbabwe Republic Police" and first.verification_status == "unverified"
    assert rows[1].is_preliminary is True
    assert record.details["reporting_period"] == "2025"


# --- scenario 5: policy --------------------------------------------------------------------


def test_scenario_5_policy_is_reviewable_news_not_an_accident_alert(session, migrated_engine):
    process(session, migrated_engine, "Government announces new toll tariffs", "New tariffs from December.", policy_reply())
    record = records(session)[0]
    assert (record.primary_category, record.primary_subtype) == ("transport_policy", "toll_fee_change")
    assert record.details["amounts"][0]["currency"] == "USD" and record.details["effective_date"] == "2026-12-01"
    assert session.scalar(select(func.count()).select_from(Incident)) == 0
    assert session.scalar(select(func.count()).select_from(PublicAlert)) == 0


# --- scenario 6: false positive -------------------------------------------------------------


def test_scenario_6_a_stock_market_crash_is_filtered_before_any_fetch_or_ai_call(session, migrated_engine):
    item = add_item(session, title="Zimbabwe Stock Exchange crashes", excerpt="Share prices fell sharply on Monday.")
    fetch, extractor = FakeFetch(), IntelExtractor()
    summary = runner(migrated_engine, fetch, extractor).run()
    session.expire_all()
    session.refresh(item)
    assert item.processing_status == "filtered" and summary.filtered == 1
    assert fetch.calls == [] and extractor.calls == []
    assert item.source_metadata["screening"]["reason_code"] == "false_positive_context"
    assert "non-transport context" in item.screen_reason


# --- scenario 7: Zimbabwe relevance ----------------------------------------------------------


def test_scenario_7_a_foreign_crash_is_not_relevant_just_because_the_publisher_is_zimbabwean(session, migrated_engine):
    item = add_item(session, title="Bus accident kills 20 in South Africa", excerpt="A bus left the road near Durban.")
    fetch = FakeFetch()
    runner(migrated_engine, fetch, IntelExtractor()).run()
    session.expire_all()
    session.refresh(item)
    assert item.processing_status == "filtered" and fetch.calls == []
    assert item.source_metadata["screening"]["reason_code"] == "no_zimbabwe_connection"


def test_scenario_7_a_material_zimbabwe_connection_qualifies_as_regional(session, migrated_engine):
    item, _, extractor = process(
        session, migrated_engine, "Zimbabwean passengers killed in South Africa bus crash",
        "A Beitbridge-bound bus crashed.", intel_reply(geographic_scope="regional"),
    )
    assert extractor.calls and records(session)[0].geographic_scope == "regional"
    assert item.source_metadata["screening"]["geographical_relevance"] == "regional"


# --- irrelevant per the model ----------------------------------------------------------------


def test_an_item_the_model_calls_irrelevant_is_discarded_without_a_record(session, migrated_engine):
    item, summary, _ = process(session, migrated_engine, "Kombi fares row", "Fare dispute.",
                               intel_reply(is_transport_relevant=False))
    assert records(session) == [] and status(session, item) == "discarded"
    assert item.source_metadata["discard_reason"] == "not_transport_relevant" and summary.intelligence_records == 0


def test_a_low_confidence_classification_is_discarded(session, migrated_engine):
    item, _, _ = process(session, migrated_engine, "Kombi fares row", "Fare dispute.",
                         intel_reply(classification_confidence=0.2))
    assert records(session) == [] and item.source_metadata["discard_reason"] == "low_confidence"


def test_one_source_item_gets_one_record_per_extraction_version(session, migrated_engine, db_error):
    process(session, migrated_engine, "ZINARA announces road rehabilitation", "Rehab.", infrastructure_reply())
    record = records(session)[0]
    with db_error(session, "23505"):
        session.add(IntelligenceRecord(
            source_item_id=record.source_item_id, extraction_version=record.extraction_version,
            taxonomy_version="x", primary_category="road_safety", record_kind="advisory",
            temporal_status="unknown", geographic_scope="unknown", classification_confidence=0.5,
            headline="h", neutral_summary="s",
        ))


# --- integrity ----------------------------------------------------------------------------------


def base_record(session, **overrides):
    source = f.make_source(session)
    item = f.make_source_item(session, source)
    values = dict(
        source_item_id=item.id, extraction_version="transport-intel-v1", taxonomy_version="2026.11.1",
        primary_category="transport_policy", primary_subtype="toll_fee_change",
        record_kind="informational_development", temporal_status="unknown", geographic_scope="national",
        classification_confidence=0.8, headline="Toll fees change", neutral_summary="Toll fees change.",
    )
    values.update(overrides)
    record = IntelligenceRecord(**values)
    session.add(record)
    session.flush()
    return record


def test_policy_and_statistics_records_cannot_be_linked_to_an_incident(session, db_error):
    incident = f.make_incident(session)
    record = base_record(session)
    with db_error(session, "23514"):
        record.incident_id = incident.id
        session.flush()


def test_an_actionable_record_may_link_to_an_incident(session):
    incident = f.make_incident(session)
    record = base_record(session, primary_category="road_incident", primary_subtype="collision",
                         record_kind="actionable_event", incident_id=incident.id)
    assert record.incident_id == incident.id


def test_a_subtype_must_belong_to_its_category(session, db_error):
    with db_error(session, "23514"):
        base_record(session, primary_category="road_incident", primary_subtype="toll_fee_change")


def test_unknown_categories_and_kinds_are_rejected_by_the_database(session, db_error):
    with db_error(session, "23514"):
        base_record(session, primary_category="weather", primary_subtype=None)


def test_incident_types_for_closures_are_accepted_and_junk_still_is_not(session, db_error):
    assert f.make_incident(session, incident_type="road_closure").incident_type == "road_closure"
    assert f.make_incident(session, incident_type="traffic_disruption").incident_type == "traffic_disruption"
    with db_error(session, "23514"):
        f.make_incident(session, incident_type="meteor")


def test_existing_incidents_remain_readable_without_intelligence_records(session):
    incident = f.make_incident(session, incident_type="collision")
    assert session.get(Incident, incident.id).incident_type == "collision"
    assert records(session) == []


def test_verified_figures_need_a_verifier(session, db_error):
    record = base_record(session)
    with db_error(session, "23514"):
        session.add(StatisticalObservation(record_id=record.id, metric="deaths", value=1, unit="persons",
                                           verification_status="verified"))


def version(session, record, number, editor, headline="Headline"):
    v = IntelligenceVersion(
        record_id=record.id, version_number=number, headline=headline, summary="Summary",
        primary_category=record.primary_category, primary_subtype=record.primary_subtype,
        geographic_scope=record.geographic_scope, created_by=editor.id,
    )
    session.add(v)
    session.flush()
    return v


def review(session, record, v, user, decision="approved"):
    r = IntelligenceReview(record_id=record.id, version_id=v.id if v else None, reviewer_id=user.id, decision=decision)
    session.add(r)
    session.flush()
    return r


def test_a_record_cannot_be_approved_without_an_approving_review(session, db_error):
    record = base_record(session)
    with db_error(session, "23514"):
        record.status = "approved"
        session.flush()


def test_only_active_human_editors_can_review(session, db_error):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v = version(session, record, 1, editor)
    with db_error(session, "23514"):
        review(session, record, v, f.make_user(session, "service"))


def test_versions_and_reviews_are_append_only(session, db_error):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v = version(session, record, 1, editor)
    r = review(session, record, v, editor)
    with db_error(session, "23001"):
        v.headline = "Silently changed"
        session.flush()
    with db_error(session, "23001"):
        r.decision = "rejected"
        session.flush()


def test_an_approval_must_cover_the_latest_version(session, db_error):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v1 = version(session, record, 1, editor)
    version(session, record, 2, editor, "Corrected headline")
    with db_error(session, "23514"):
        review(session, record, v1, editor)


def publish(session, record, v, approval, editor, output="transport_news"):
    out = PublicationOutput(record_id=record.id, version_id=v.id, approval_review_id=approval.id,
                            output_type=output, published_by=editor.id)
    session.add(out)
    session.flush()
    return out


def test_publication_is_a_separate_action_on_an_exactly_approved_version(session):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v1 = version(session, record, 1, editor)
    approval = review(session, record, v1, editor)
    record.status = "approved"
    session.flush()
    assert session.scalar(select(func.count()).select_from(PublicationOutput)) == 0  # approval alone publishes nothing
    out = publish(session, record, v1, approval, editor)
    assert out.status == "published" and out.output_type == "transport_news"


def test_a_rejected_or_superseded_review_cannot_back_a_publication(session, db_error):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v1 = version(session, record, 1, editor)
    rejected = review(session, record, v1, editor, "rejected")
    with db_error(session, "23514"):
        publish(session, record, v1, rejected, editor)

    approval = review(session, record, v1, editor, "approved")
    review(session, record, v1, editor, "needs_changes")  # a later decision supersedes the approval
    with db_error(session, "23514"):
        publish(session, record, v1, approval, editor)


def test_an_older_version_cannot_be_published_after_an_edit(session, db_error):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v1 = version(session, record, 1, editor)
    approval = review(session, record, v1, editor)
    version(session, record, 2, editor, "Edited after approval")
    with db_error(session, "23514"):
        publish(session, record, v1, approval, editor)


def test_the_same_version_cannot_be_published_twice_as_one_output(session, db_error):
    record = base_record(session)
    editor = f.make_user(session, "editor")
    v1 = version(session, record, 1, editor)
    approval = review(session, record, v1, editor)
    publish(session, record, v1, approval, editor)
    with db_error(session, "23505"):
        publish(session, record, v1, approval, editor)
    publish(session, record, v1, approval, editor, "statistical_insight")  # a different output is fine


def test_source_items_remain_untouched_by_classification(session, migrated_engine):
    item, _, _ = process(session, migrated_engine, "ZINARA announces road rehabilitation", "Rehab.", infrastructure_reply())
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 1
    assert item.article_text_redacted  # original (redacted) content stays on the source item only


# --- cost control -----------------------------------------------------------------------------------


def test_categories_of_interest_filter_before_any_fetch_or_ai_call(session, migrated_engine):
    item = add_item(session, title="Government announces new toll tariffs", excerpt="New tariffs from December.")
    fetch, extractor = FakeFetch(), IntelExtractor()
    summary = runner(migrated_engine, fetch, extractor, enabled_categories=frozenset({"road_incident"})).run()
    session.expire_all()
    session.refresh(item)
    assert item.processing_status == "filtered" and summary.filtered == 1
    assert fetch.calls == [] and extractor.calls == []
    assert item.source_metadata["screening"]["reason_code"] == "category_not_enabled"


def test_an_enabled_category_still_goes_through(session, migrated_engine):
    item = add_item(session, title="Government announces new toll tariffs", excerpt="New tariffs from December.")
    extractor = IntelExtractor(policy_reply())
    runner(migrated_engine, FakeFetch(), extractor, enabled_categories=frozenset({"transport_policy"})).run()
    assert extractor.calls and records(session)[0].primary_category == "transport_policy"


def test_the_enabled_category_setting_is_validated():
    from app.services.pipeline import parse_categories

    assert parse_categories("") is None and parse_categories(None) is None
    assert parse_categories(" road_incident , transport_policy ") == frozenset({"road_incident", "transport_policy"})
    with pytest.raises(ValueError):
        parse_categories("road_incident,weather")
