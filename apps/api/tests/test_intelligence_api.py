"""Intelligence API: filters, categories, statistics, editorial workflow and the public view.

Synthetic data only. Public responses must never carry internal AI or editorial fields.
"""

from datetime import date

import pytest

import db_factories as f
from api_helpers import sign_in
from app.models.intelligence import StatisticalObservation
from test_intelligence_pipeline import base_record

pytestmark = pytest.mark.usefixtures("migrated_engine")

V1 = "/api/v1"
INTERNAL_ONLY = {"classification_confidence", "quality", "details", "needs_editorial_review", "notes", "reviewer_name",
                 "topic_key", "extraction_version", "taxonomy_version", "incident_id", "status"}


def code(response):
    return response.json()["error"]["code"]


def make_record(session, **overrides):
    record = base_record(session, **overrides)
    session.commit()
    return record


def add_stat(session, record, metric="road deaths", value=1800, **overrides):
    values = dict(record_id=record.id, metric=metric, value=value, unit="persons",
                  period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
                  geographic_coverage="Zimbabwe", source_reference="Zimbabwe Republic Police")
    values.update(overrides)
    obs = StatisticalObservation(**values)
    session.add(obs)
    session.commit()
    return obs


def version_body(record, base=None, **overrides):
    body = {"headline": "Toll fees change", "summary": "Toll fees will change from December.",
            "primary_category": record.primary_category, "primary_subtype": record.primary_subtype,
            "geographic_scope": "national", "event_date": None, "base_version": base}
    body.update(overrides)
    return body


def approve(client, headers, record, **version_overrides):
    v = client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record, **version_overrides), headers=headers)
    assert v.status_code == 201, v.text
    r = client.post(f"{V1}/intelligence/{record.id}/reviews",
                    json={"decision": "approved", "version_id": v.json()["id"]}, headers=headers)
    assert r.status_code == 201, r.text
    return v.json(), r.json()


# --- reading --------------------------------------------------------------------------------------


def test_the_list_requires_a_signed_in_reader(client, session):
    assert client.get(f"{V1}/intelligence").status_code == 401


def test_filters_by_category_kind_status_text_and_confidence(client, session):
    make_record(session, headline="Toll fees change", neutral_summary="Tariffs", classification_confidence=0.9)
    make_record(session, primary_category="road_safety_data", primary_subtype="annual_report",
                record_kind="statistical_report", headline="Annual report", neutral_summary="Yearly figures",
                classification_confidence=0.5,
                province="Harare")
    sign_in(client, session, "analyst")

    def total(**params):
        r = client.get(f"{V1}/intelligence", params=params)
        assert r.status_code == 200, r.text
        return r.json()["total"]

    assert total() == 2
    assert total(category="transport_policy") == 1
    assert total(record_kind="statistical_report") == 1
    assert total(subtype="annual_report") == 1
    assert total(status="candidate") == 2 and total(status="published") == 0
    assert total(q="toll") == 1 and total(q="TARIFFS") == 1
    assert total(min_confidence=0.8) == 1
    assert total(province="harare") == 1
    assert total(has_incident=False) == 2 and total(has_incident=True) == 0
    assert total(category="road_hazard") == 0


def test_date_range_filters_use_the_event_date_or_creation_date(client, session):
    make_record(session, event_date=date(2025, 6, 1))
    sign_in(client, session, "analyst")
    assert client.get(f"{V1}/intelligence", params={"date_from": "2025-05-01", "date_to": "2025-07-01"}).json()["total"] == 1
    assert client.get(f"{V1}/intelligence", params={"date_from": "2025-07-02"}).json()["total"] == 0


def test_pagination_is_bounded_and_sorting_is_stable(client, session):
    for i in range(3):
        make_record(session, headline=f"Item {i}")
    sign_in(client, session, "analyst")
    assert client.get(f"{V1}/intelligence", params={"page_size": 1000}).status_code == 422
    first = [client.get(f"{V1}/intelligence", params={"page_size": 2, "page": p}).json() for p in (1, 2)]
    ids = [i["id"] for page in first for i in page["items"]]
    assert len(ids) == 3 == len(set(ids))
    again = client.get(f"{V1}/intelligence", params={"page_size": 3}).json()["items"]
    assert [i["id"] for i in again] == ids


def test_unknown_filter_values_are_rejected(client, session):
    sign_in(client, session, "analyst")
    assert client.get(f"{V1}/intelligence", params={"category": "weather"}).status_code == 422
    assert client.get(f"{V1}/intelligence", params={"record_kind": "rumour"}).status_code == 422


def test_categories_endpoint_lists_the_whole_taxonomy_with_counts(client, session):
    make_record(session)
    sign_in(client, session, "analyst")
    body = client.get(f"{V1}/intelligence/categories").json()
    assert len(body["categories"]) == 10 and "actionable_event" in body["record_kinds"]
    policy = next(c for c in body["categories"] if c["category"] == "transport_policy")
    assert (policy["total"], policy["awaiting_review"], policy["published"]) == (1, 1, 0)
    assert "toll_fee_change" in policy["subtypes"]


def test_detail_shows_citations_quality_and_allowed_outputs_to_editors(client, session):
    record = make_record(session, quality={"flags": ["figures_unverified"]}, details={"policy_or_regulation": "Tolls"})
    sign_in(client, session, "analyst")
    body = client.get(f"{V1}/intelligence/{record.id}").json()
    assert body["citations"][0]["source_name"] and body["quality"]["flags"] == ["figures_unverified"]
    assert body["details"]["policy_or_regulation"] == "Tolls"
    assert "statistical_insight" not in body["allowed_outputs"] and "transport_news" in body["allowed_outputs"]
    assert client.get(f"{V1}/intelligence/00000000-0000-0000-0000-000000000000").status_code == 404


def test_statistics_keep_periods_separate_and_never_sum(client, session):
    record = make_record(session, primary_category="road_safety_data", primary_subtype="fatality_statistics",
                         record_kind="statistical_report")
    add_stat(session, record, value=1800)
    add_stat(session, record, value=1700, period_start=date(2024, 1, 1), period_end=date(2024, 12, 31))
    add_stat(session, record, value=5, geographic_coverage="Harare")
    sign_in(client, session, "analyst")
    body = client.get(f"{V1}/intelligence/statistics", params={"metric": "road deaths"}).json()
    assert len(body["series"]) == 2  # national vs Harare coverage are separate series
    national = next(s for s in body["series"] if s["geographic_coverage"] == "Zimbabwe")
    assert [p["value"] for p in national["points"]] == [1700, 1800]  # ordered by period, not merged
    assert "not added together" in body["note"] and national["points"][0]["verification_status"] == "unverified"
    assert client.get(f"{V1}/intelligence/statistics", params={"verified_only": True}).json()["series"] == []


def test_trends_flag_thin_data_and_label_their_basis(client, session):
    make_record(session)
    sign_in(client, session, "analyst")
    body = client.get(f"{V1}/intelligence/trends", params={"months": 6}).json()
    assert body["total"] == 1 and body["sufficient_data"] is False
    assert "not comparable" in body["caveat"] and body["points"][0]["category"] == "transport_policy"
    assert client.get(f"{V1}/intelligence/trends", params={"months": 99}).status_code == 422


def test_insights_group_related_coverage_only_when_more_than_one_record(client, session):
    make_record(session, topic_key="transport_policy:toll-tariffs")
    sign_in(client, session, "analyst")
    assert client.get(f"{V1}/intelligence/insights").json()["topic_groups"] == []
    make_record(session, topic_key="transport_policy:toll-tariffs")
    body = client.get(f"{V1}/intelligence/insights").json()
    assert body["topic_groups"][0]["record_count"] == 2 and "Verify" in body["caveat"]


# --- editorial workflow ---------------------------------------------------------------------------


def test_analysts_cannot_change_or_publish(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "analyst")
    assert client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record), headers=headers).status_code == 403
    assert client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers).status_code == 403


def test_an_editor_can_correct_category_subtype_scope_and_summary(client, session):
    record = make_record(session, primary_category="other_transport_intelligence", primary_subtype="other",
                         record_kind="unknown", geographic_scope="unknown")
    _, headers = sign_in(client, session, "editor")
    body = version_body(record, primary_category="transport_policy", primary_subtype="toll_fee_change",
                        geographic_scope="national", change_note="Reclassified")
    response = client.post(f"{V1}/intelligence/{record.id}/versions", json=body, headers=headers)
    assert response.status_code == 201 and response.json()["version_number"] == 1
    session.expire_all()
    session.refresh(record)
    assert (record.primary_category, record.primary_subtype, record.status) == ("transport_policy", "toll_fee_change", "under_review")
    detail = client.get(f"{V1}/intelligence/{record.id}").json()
    assert detail["versions"][0]["change_note"] == "Reclassified" and detail["versions"][0]["is_latest"]


def test_a_subtype_of_another_category_is_rejected(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    r = client.post(f"{V1}/intelligence/{record.id}/versions",
                    json=version_body(record, primary_subtype="pothole"), headers=headers)
    assert r.status_code == 422 and code(r) == "INVALID_SUBTYPE"


def test_personal_data_in_a_summary_is_blocked(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    r = client.post(f"{V1}/intelligence/{record.id}/versions",
                    json=version_body(record, summary="Call 0772 123 456 for details."), headers=headers)
    assert r.status_code == 422


def test_version_saves_use_optimistic_concurrency(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    assert client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record), headers=headers).status_code == 201
    stale = client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record, base=None), headers=headers)
    assert stale.status_code == 409 and code(stale) == "VERSION_CONFLICT"


def test_an_incident_linked_record_must_stay_actionable(client, session):
    incident = f.make_incident(session)
    record = make_record(session, primary_category="road_incident", primary_subtype="collision",
                          record_kind="actionable_event", incident_id=incident.id)
    _, headers = sign_in(client, session, "editor")
    r = client.post(f"{V1}/intelligence/{record.id}/versions",
                    json=version_body(record, primary_category="transport_policy", primary_subtype=None), headers=headers)
    assert r.status_code == 409 and code(r) == "RECORD_LINKED_TO_INCIDENT"


def test_approval_needs_the_exact_latest_version_and_every_figure_decided(client, session):
    record = make_record(session, primary_category="road_safety_data", primary_subtype="fatality_statistics",
                         record_kind="statistical_report")
    obs = add_stat(session, record)
    _, headers = sign_in(client, session, "editor")
    v1 = client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record), headers=headers).json()
    blocked = client.post(f"{V1}/intelligence/{record.id}/reviews",
                          json={"decision": "approved", "version_id": v1["id"]}, headers=headers)
    assert blocked.status_code == 409 and code(blocked) == "UNVERIFIED_FIGURES"

    v2 = client.post(f"{V1}/intelligence/{record.id}/versions", headers=headers, json=version_body(
        record, base=1, figure_decisions=[{"observation_id": str(obs.id), "status": "verified"}])).json()
    assert v2["figures"][0]["verification_status"] == "verified"
    stale = client.post(f"{V1}/intelligence/{record.id}/reviews",
                        json={"decision": "approved", "version_id": v1["id"]}, headers=headers)
    assert stale.status_code == 409 and code(stale) == "STALE_VERSION"
    ok = client.post(f"{V1}/intelligence/{record.id}/reviews",
                     json={"decision": "approved", "version_id": v2["id"]}, headers=headers)
    assert ok.status_code == 201 and ok.json()["status"] == "approved"
    assert ok.json()["reviews"][0]["reviewer_name"]


def test_rejecting_requires_notes(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record), headers=headers)
    r = client.post(f"{V1}/intelligence/{record.id}/reviews", json={"decision": "rejected"}, headers=headers)
    assert r.status_code == 422 and code(r) == "NOTES_REQUIRED"
    ok = client.post(f"{V1}/intelligence/{record.id}/reviews", json={"decision": "rejected", "notes": "Not relevant"}, headers=headers)
    assert ok.status_code == 201 and ok.json()["status"] == "rejected"


def test_editing_after_approval_reopens_review_and_blocks_publication(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    approve(client, headers, record)
    client.post(f"{V1}/intelligence/{record.id}/versions", json=version_body(record, base=1, headline="Edited"), headers=headers)
    r = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers)
    assert r.status_code == 409 and code(r) == "RECORD_NOT_APPROVED"


def test_approval_alone_publishes_nothing(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    approve(client, headers, record)
    assert client.get(f"{V1}/public/transport/news").json()["total"] == 0
    detail = client.get(f"{V1}/intelligence/{record.id}").json()
    assert detail["status"] == "approved" and detail["outputs"] == []


def test_publish_is_separate_and_limited_to_allowed_outputs(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    unapproved = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers)
    assert unapproved.status_code == 409
    approve(client, headers, record)
    not_allowed = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "statistical_insight"}, headers=headers)
    assert not_allowed.status_code == 422 and code(not_allowed) == "OUTPUT_NOT_ALLOWED"
    ok = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers)
    assert ok.status_code == 201 and ok.json()["status"] == "published"
    assert ok.json()["outputs"][0]["output_type"] == "transport_news"
    again = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers)
    assert again.status_code == 409 and code(again) == "ALREADY_PUBLISHED"


def test_a_statistical_insight_needs_a_verified_figure(client, session):
    record = make_record(session, primary_category="road_safety_data", primary_subtype="annual_report",
                         record_kind="statistical_report")
    _, headers = sign_in(client, session, "editor")
    approve(client, headers, record)  # no figures at all
    r = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "statistical_insight"}, headers=headers)
    assert r.status_code == 409 and code(r) == "NO_VERIFIED_FIGURES"


# --- public view ----------------------------------------------------------------------------------


def keys(node):
    found = set()
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            found |= keys(v)
    elif isinstance(node, list):
        for v in node:
            found |= keys(v)
    return found


def test_public_endpoints_show_only_published_privacy_safe_items(client, session):
    record = make_record(session)
    hidden = make_record(session, headline="Never public")  # a candidate
    _, headers = sign_in(client, session, "editor")
    approve(client, headers, record)
    client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers)

    body = client.get(f"{V1}/public/transport/news").json()
    assert body["total"] == 1 and body["items"][0]["headline"] == "Toll fees change"
    assert body["items"][0]["category"] == "transport_policy"
    assert keys(body).isdisjoint(INTERNAL_ONLY)
    assert hidden.headline not in str(body)
    assert client.get(f"{V1}/public/transport/news", params={"category": "road_hazard"}).json()["total"] == 0
    assert client.get(f"{V1}/public/transport/insights").json()["total"] == 0  # a news item is not an insight


def test_public_statistics_show_only_verified_figures_of_published_statistical_records(client, session):
    record = make_record(session, primary_category="road_safety_data", primary_subtype="fatality_statistics",
                         record_kind="statistical_report")
    verified = add_stat(session, record, metric="road deaths", value=1800)
    add_stat(session, record, metric="road injuries", value=9000)  # left unverified
    _, headers = sign_in(client, session, "editor")
    assert client.get(f"{V1}/public/transport/statistics").json()["statistics"] == []
    approve(client, headers, record, figure_decisions=[
        {"observation_id": str(verified.id), "status": "verified"},
        {"observation_id": str(session.query(StatisticalObservation).filter_by(metric="road injuries").one().id), "status": "rejected"},
    ])
    r = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "statistical_insight"}, headers=headers)
    assert r.status_code == 201, r.text
    body = client.get(f"{V1}/public/transport/statistics").json()
    assert [(s["metric"], s["value"], s["unit"], s["source_reference"]) for s in body["statistics"]] == [
        ("road deaths", 1800.0, "persons", "Zimbabwe Republic Police")]
    assert body["statistics"][0]["period_start"] == "2025-01-01" and "not added together" in body["note"]
    assert keys(body).isdisjoint(INTERNAL_ONLY | {"verification_status", "verified_by"})
    assert client.get(f"{V1}/public/transport/insights").json()["total"] == 1


def test_withdrawing_removes_the_item_from_the_public_site(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    approve(client, headers, record)
    published = client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers).json()
    output_id = published["outputs"][0]["id"]
    assert client.get(f"{V1}/public/transport/news").json()["total"] == 1
    assert client.post(f"{V1}/intelligence/outputs/{output_id}/withdraw", headers=headers).status_code == 200
    assert client.get(f"{V1}/public/transport/news").json()["total"] == 0
    assert client.get(f"{V1}/intelligence/{record.id}").json()["status"] == "approved"


def test_publishing_intelligence_never_creates_a_hazard_alert(client, session):
    record = make_record(session)
    _, headers = sign_in(client, session, "editor")
    approve(client, headers, record)
    client.post(f"{V1}/intelligence/{record.id}/publish", json={"output_type": "transport_news"}, headers=headers)
    alerts = client.get(f"{V1}/public/alerts").json()
    assert alerts["total"] == 0
    assert client.get(f"{V1}/public/map").json()["features"] == []


def test_old_incident_endpoints_are_unchanged_by_intelligence_records(client, session):
    f.make_incident(session)
    make_record(session)
    sign_in(client, session, "analyst")
    page = client.get(f"{V1}/incidents").json()
    assert page["total"] == 1  # the policy record is not an incident


# --- news API -------------------------------------------------------------------------------------


def test_news_items_expose_classification_and_filter_by_category(client, session):
    record = make_record(session, primary_category="road_infrastructure", primary_subtype="road_rehabilitation",
                         record_kind="informational_development")
    other = f.make_source_item(session, f.make_source(session), title_redacted="Unclassified item",
                               processing_status="screened",
                               source_metadata={"screening": {"categories": ["road_incident"], "geographical_relevance": "zimbabwe"}})
    session.commit()
    sign_in(client, session, "analyst")
    items = client.get(f"{V1}/news", params={"page_size": 50}).json()["items"]
    by_id = {i["id"]: i for i in items}
    classified = by_id[str(record.source_item_id)]["classification"]
    assert (classified["status"], classified["primary_category"], classified["record_kind"]) == (
        "classified", "road_infrastructure", "informational_development")
    assert classified["intelligence_record_id"] == str(record.id) and classified["linked_incident_id"] is None
    waiting = by_id[str(other.id)]["classification"]
    assert waiting["status"] == "awaiting_classification" and waiting["candidate_categories"] == ["road_incident"]
    assert waiting["geographic_relevance"] == "zimbabwe" and by_id[str(other.id)]["source_platform"]

    def ids(**params):
        return {i["id"] for i in client.get(f"{V1}/news", params=params).json()["items"]}

    assert ids(category="road_infrastructure") == {str(record.source_item_id)}
    assert ids(category="road_incident") == {str(other.id)}  # keyword-screen candidate before classification
    assert ids(record_kind="informational_development") == {str(record.source_item_id)}
    assert client.get(f"{V1}/news", params={"category": "nonsense"}).status_code == 422


def test_news_detail_includes_the_classification_block(client, session):
    record = make_record(session)
    sign_in(client, session, "analyst")
    body = client.get(f"{V1}/news/{record.source_item_id}").json()
    assert body["classification"]["primary_category"] == "transport_policy"

