"""Unified classification schema: validation, taxonomy rules and the incident-shaped view.

No database, network or OpenAI key. Replies are synthetic, mocked model output.
"""

import json

import pytest
from pydantic import ValidationError

from app.schemas.intelligence import INTELLIGENCE_JSON_SCHEMA, DataQualityFlag, IntelligenceExtraction
from app.taxonomy import SUBTYPES, PrimaryCategory, may_create_incident, taxonomy_as_dict
from intel_helpers import (
    BLOCKS,
    blank_details,
    closure_reply,
    infrastructure_reply,
    intel_reply,
    policy_reply,
    stat,
    statistics_reply,
)


def parse(reply: dict) -> IntelligenceExtraction:
    return IntelligenceExtraction.model_validate(reply)


# --------------------------------------------------------------------------- taxonomy


def test_every_category_has_subtypes_and_the_spec_counts():
    assert len(PrimaryCategory) == 11  # ten transport categories + city_news (regional deployments)
    assert {c: len(s) for c, s in SUBTYPES.items()} == {
        PrimaryCategory.ROAD_INCIDENT: 11, PrimaryCategory.TRAFFIC_DISRUPTION: 10,
        PrimaryCategory.ROAD_HAZARD: 11, PrimaryCategory.ROAD_INFRASTRUCTURE: 10,
        PrimaryCategory.PUBLIC_TRANSPORT: 10, PrimaryCategory.FREIGHT_AND_LOGISTICS: 8,
        PrimaryCategory.ROAD_SAFETY: 9, PrimaryCategory.ROAD_SAFETY_DATA: 9,
        PrimaryCategory.TRANSPORT_POLICY: 9, PrimaryCategory.OTHER_TRANSPORT_INTELLIGENCE: 1,
        PrimaryCategory.CITY_NEWS: 9,
    }


def test_the_taxonomy_export_is_json_serialisable_and_versioned():
    data = json.loads(json.dumps(taxonomy_as_dict()))
    assert data["version"] and "road_safety_data" in data["categories"]


@pytest.mark.parametrize(
    ("category", "kind", "allowed"),
    [
        ("road_incident", "actionable_event", True),
        ("traffic_disruption", "actionable_event", True),
        ("road_hazard", "actionable_event", True),
        ("road_infrastructure", "actionable_event", False),
        ("road_safety_data", "statistical_report", False),
        ("transport_policy", "informational_development", False),
        ("road_incident", "statistical_report", False),
        ("nonsense", "actionable_event", False),
    ],
)
def test_only_actionable_events_in_actionable_categories_may_create_incidents(category, kind, allowed):
    assert may_create_incident(category, kind) is allowed


# --------------------------------------------------------------------------- schema


def test_the_json_schema_is_strict_everywhere():
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(INTELLIGENCE_JSON_SCHEMA)
    assert "allOf" not in json.dumps(INTELLIGENCE_JSON_SCHEMA)


def test_the_schema_constrains_categories_to_the_central_taxonomy():
    defs = INTELLIGENCE_JSON_SCHEMA["$defs"]
    assert set(defs["PrimaryCategory"]["enum"]) == {c.value for c in PrimaryCategory}
    assert set(defs["RecordKind"]["enum"]) >= {"actionable_event", "statistical_report"}


# --------------------------------------------------------------------------- per-category payloads


@pytest.mark.parametrize(
    ("reply", "block"),
    [
        (intel_reply(), "road_incident"),
        (closure_reply(), "traffic_disruption"),
        (infrastructure_reply(), "road_infrastructure"),
        (statistics_reply(), "road_safety_data"),
        (policy_reply(), "transport_policy"),
    ],
)
def test_the_block_for_the_primary_category_is_exposed(reply, block):
    extraction = parse(reply)
    assert extraction.category_details is not None
    assert extraction.details_json() == extraction.details.model_dump(mode="json")[block]


@pytest.mark.parametrize(
    ("category", "subtype", "block", "payload"),
    [
        ("road_hazard", "pothole", "road_hazard", {
            "hazard_type": "pothole", "road_segment": "Seke Road", "reported_condition": None,
            "traffic_effect": None, "starts_on": None, "ends_on": None}),
        ("public_transport", "fare_change", "public_transport", {
            "operator": "ZUPCO", "service_or_route": None,
            "fare_changes": [{"description": "urban fare", "amount": 1.0, "currency": "USD"}],
            "effective_date": "2026-12-01", "affected_passengers_or_services": None}),
        ("freight_and_logistics", "truck_queue", "freight_and_logistics", {
            "border_post": "Beitbridge", "corridor": None, "restriction_type": None,
            "queue_or_delay": "about 5km", "vehicle_class": "heavy goods"}),
        ("road_safety", "road_safety_campaign", "road_safety", {
            "organisation": "TSCZ", "initiative_type": "campaign", "target_population": None,
            "announced_dates": None, "measures": None}),
    ],
)
def test_other_category_payloads_validate(category, subtype, block, payload):
    extraction = parse(intel_reply(
        primary_category=category, primary_subtype=subtype, record_kind="informational_development",
        details=blank_details(**{block: payload}),
    ))
    assert extraction.primary_category.value == category
    assert extraction.category_details is not None


def test_other_transport_intelligence_requires_an_explanation_or_is_flagged_for_review():
    extraction = parse(intel_reply(
        primary_category="other_transport_intelligence", primary_subtype=None,
        record_kind="unknown", needs_editorial_review=False, details=blank_details(),
    ))
    assert DataQualityFlag.MISSING_EXPLANATION in extraction.data_quality_flags
    assert extraction.needs_editorial_review is True


# --------------------------------------------------------------------------- rules enforced in code


def test_a_subtype_from_another_category_is_dropped_and_flagged_not_trusted():
    extraction = parse(intel_reply(primary_category="road_incident", primary_subtype="toll_fee_change"))
    assert extraction.primary_subtype is None
    assert DataQualityFlag.SUBTYPE_MISMATCH in extraction.data_quality_flags


def test_statistics_can_never_be_an_incident_even_if_the_model_says_actionable():
    extraction = parse(statistics_reply(record_kind="actionable_event"))
    assert extraction.record_kind.value == "statistical_report"
    assert DataQualityFlag.KIND_ADJUSTED in extraction.data_quality_flags
    assert extraction.creates_incident is False
    assert extraction.to_legacy_result().is_road_incident is False


def test_policy_and_infrastructure_announcements_never_become_incidents():
    for reply in (policy_reply(record_kind="actionable_event"), infrastructure_reply(record_kind="actionable_event")):
        extraction = parse(reply)
        assert extraction.record_kind.value == "informational_development"
        assert extraction.to_legacy_result().is_road_incident is False


def test_an_aggregate_report_in_an_incident_category_is_not_a_new_incident():
    extraction = parse(intel_reply(record_kind="statistical_report", temporal_status="historical"))
    assert extraction.to_legacy_result().is_road_incident is False


def test_an_irrelevant_article_is_never_an_incident():
    assert parse(intel_reply(is_transport_relevant=False)).to_legacy_result().is_road_incident is False


def test_the_incident_view_carries_only_stated_facts():
    result = parse(intel_reply()).to_legacy_result()
    assert result.is_road_incident and result.incident_type.value == "rollover"
    assert (result.fatalities, result.injuries, result.severity.value) == (3, 5, "fatal")
    assert result.location_text == "Harare-Mutare road near Rusape"


def test_a_closure_becomes_a_road_closure_incident_type():
    result = parse(closure_reply()).to_legacy_result()
    assert result.is_road_incident and result.incident_type.value == "road_closure"


def test_missing_counts_stay_null_instead_of_being_invented():
    block = intel_reply()["details"]["road_incident"] | {"fatalities": None, "injuries": None, "severity": "unknown"}
    result = parse(intel_reply(details=blank_details(road_incident=block))).to_legacy_result()
    assert (result.fatalities, result.injuries, result.severity.value) == (None, None, "unknown")


# --------------------------------------------------------------------------- statistics


def test_statistical_observations_keep_period_unit_coverage_and_source():
    extraction = parse(statistics_reply(statistics=[
        stat("road deaths", 1800), stat("road injuries", 9000.5, "persons", is_preliminary=True),
    ]))
    first, second = extraction.statistics
    assert (first.metric, first.value, first.unit) == ("road deaths", 1800.0, "persons")
    assert (first.period_start.isoformat(), first.period_end.isoformat()) == ("2025-01-01", "2025-12-31")
    assert first.source_reference == "Zimbabwe Republic Police" and second.is_preliminary is True


def test_an_observation_period_cannot_end_before_it_starts():
    with pytest.raises(ValidationError):
        parse(statistics_reply(statistics=[stat(period_start="2025-12-31", period_end="2025-01-01")]))


# --------------------------------------------------------------------------- invalid output


@pytest.mark.parametrize(
    "bad",
    [
        {"primary_category": "weather"},
        {"record_kind": "rumour"},
        {"temporal_status": "soon"},
        {"geographic_scope": "planet"},
        {"classification_confidence": 1.5},
        {"primary_subtype": "made_up_subtype"},
        {"event_or_announcement_date": "not a date"},
        {"surprise_field": 1},
    ],
)
def test_invalid_model_output_is_rejected(bad):
    with pytest.raises(ValidationError):
        parse(intel_reply(**bad))


@pytest.mark.parametrize("missing", ["primary_category", "record_kind", "details", "statistics", "neutral_summary"])
def test_missing_required_fields_are_rejected_not_defaulted(missing):
    reply = intel_reply()
    del reply[missing]
    with pytest.raises(ValidationError):
        parse(reply)


def test_every_details_block_is_required_so_unused_ones_are_explicit_nulls():
    reply = intel_reply()
    del reply["details"]["transport_policy"]
    with pytest.raises(ValidationError):
        parse(reply)
    assert set(intel_reply()["details"]) == set(BLOCKS)


def test_blank_strings_become_null():
    block = intel_reply()["details"]["road_incident"] | {"crash_mechanism": "   "}
    extraction = parse(intel_reply(details=blank_details(road_incident=block)))
    assert extraction.details.road_incident.crash_mechanism is None


def test_the_web_taxonomy_file_matches_the_backend_taxonomy():
    """apps/web/src/lib/taxonomy.generated.ts is generated; fail on drift (run scripts/export_taxonomy.py)."""
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    import export_taxonomy

    committed = export_taxonomy.DEFAULT_OUTPUT.read_text(encoding="utf-8")
    assert committed == export_taxonomy.render(), "regenerate with: python scripts/export_taxonomy.py"


def test_the_openapi_document_has_no_duplicate_operation_ids():
    import warnings

    from app.main import app

    app.openapi_schema = None  # force regeneration so FastAPI re-checks operation ids
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        app.openapi()


def test_strict_schema_has_no_keywords_beside_ref():
    """OpenAI strict mode rejects {"$ref": ..., "description": ...} (e.g. temporal_status)."""
    from app.schemas.intelligence import INTELLIGENCE_JSON_SCHEMA

    def walk(node):
        if isinstance(node, dict):
            assert "$ref" not in node or set(node) == {"$ref"}, node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(INTELLIGENCE_JSON_SCHEMA)
