"""Synthetic model replies in the unified transport-intelligence shape (no network, no key)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

BLOCKS = (
    "road_incident", "traffic_disruption", "road_hazard", "road_infrastructure", "public_transport",
    "freight_and_logistics", "road_safety", "road_safety_data", "transport_policy",
)


def blank_details(**blocks: Any) -> dict[str, Any]:
    details: dict[str, Any] = dict.fromkeys(BLOCKS)
    details.update(blocks)
    return details


def intel_reply(**overrides: Any) -> dict[str, Any]:
    """A valid road-incident reply (kombi rollover near Rusape); override any field."""
    reply: dict[str, Any] = {
        "is_transport_relevant": True,
        "primary_category": "road_incident",
        "primary_subtype": "vehicle_rollover",
        "secondary_categories": [],
        "record_kind": "actionable_event",
        "temporal_status": "unknown",
        "geographic_scope": "approximate_point",
        "classification_confidence": 0.9,
        "other_explanation": None,
        "short_headline": "Kombi overturns near Rusape",
        "neutral_summary": "A kombi overturned.",
        "event_or_announcement_date": "2026-11-02",
        "location_description": "Harare-Mutare road near Rusape",
        "country": "Zimbabwe",
        "province_or_region": "Manicaland",
        "district_or_town": "Rusape",
        "road_name": "Harare-Mutare road",
        "nearest_landmark": None,
        "source_attribution": None,
        "evidence_references": ["the kombi overturned"],
        "data_quality_flags": [],
        "missing_information": [],
        "needs_editorial_review": True,
        "details": blank_details(
            road_incident={
                "severity": "fatal", "vehicle_types": ["kombi"], "vehicles_involved": 1,
                "road_users": ["passengers"], "fatalities": 3, "injuries": 5,
                "crash_mechanism": "speeding", "road_obstruction": None,
                "emergency_response": None, "occurred_time": "05:30",
            }
        ),
        "statistics": [],
    }
    reply.update(deepcopy(overrides))
    return reply


def stat(metric="road deaths", value=1800, unit="persons", **overrides: Any) -> dict[str, Any]:
    row = {
        "metric": metric, "value": value, "unit": unit, "period_start": "2025-01-01",
        "period_end": "2025-12-31", "geographic_coverage": "Zimbabwe",
        "source_reference": "Zimbabwe Republic Police", "methodology": None,
        "comparison_period": None, "is_preliminary": False,
    }
    row.update(overrides)
    return row


def statistics_reply(**overrides: Any) -> dict[str, Any]:
    base = dict(
        primary_category="road_safety_data", primary_subtype="fatality_statistics",
        record_kind="statistical_report", geographic_scope="national", temporal_status="historical",
        short_headline="ZRP releases 2025 road fatality figures",
        neutral_summary="Police reported national road fatalities for 2025.",
        location_description=None, province_or_region=None, district_or_town=None, road_name=None,
        source_attribution="Zimbabwe Republic Police",
        details=blank_details(road_safety_data={
            "reporting_period": "2025", "geographic_coverage": "Zimbabwe",
            "indicator_names": ["road deaths"], "source_of_statistics": "Zimbabwe Republic Police",
            "methodology": None, "comparison_period": None, "is_preliminary": False,
            "contains_historical_dataset": False,
        }),
        statistics=[stat()],
    )
    base.update(overrides)
    return intel_reply(**base)


def infrastructure_reply(**overrides: Any) -> dict[str, Any]:
    base = dict(
        primary_category="road_infrastructure", primary_subtype="road_rehabilitation",
        record_kind="informational_development", geographic_scope="corridor", temporal_status="planned",
        short_headline="ZINARA to rehabilitate Harare-Bulawayo road",
        neutral_summary="ZINARA announced rehabilitation of the Harare-Bulawayo road.",
        location_description="Harare-Bulawayo road", province_or_region=None, district_or_town=None,
        road_name="Harare-Bulawayo road", source_attribution="ZINARA",
        details=blank_details(road_infrastructure={
            "project_name": "Harare-Bulawayo road rehabilitation", "road_segment": "Harare-Bulawayo",
            "project_type": "rehabilitation", "project_status": "announced", "cost_amount": None,
            "cost_currency": None, "contractor": None, "timeline": None,
            "traffic_disruption_confirmed": None,
        }),
    )
    base.update(overrides)
    return intel_reply(**base)


def policy_reply(**overrides: Any) -> dict[str, Any]:
    base = dict(
        primary_category="transport_policy", primary_subtype="toll_fee_change",
        record_kind="informational_development", geographic_scope="national", temporal_status="unknown",
        short_headline="Government announces new toll tariffs",
        neutral_summary="New toll tariffs were announced.",
        location_description=None, province_or_region=None, district_or_town=None, road_name=None,
        event_or_announcement_date="2026-11-03",
        details=blank_details(transport_policy={
            "responsible_institution": "Ministry of Transport", "policy_or_regulation": "Toll tariffs",
            "announcement_date": "2026-11-03", "effective_date": "2026-12-01",
            "affected_parties": "light and heavy vehicles", "obligations": None,
            "amounts": [{"description": "light vehicle toll", "amount": 2.0, "currency": "USD"}],
        }),
    )
    base.update(overrides)
    return intel_reply(**base)


def closure_reply(**overrides: Any) -> dict[str, Any]:
    base = dict(
        primary_category="traffic_disruption", primary_subtype="road_closure",
        record_kind="actionable_event", temporal_status="planned", geographic_scope="road_segment",
        short_headline="Road closed at Beitbridge for bridge repairs",
        neutral_summary="A road will be closed for bridge repairs.",
        location_description="Beitbridge", province_or_region="Matabeleland South",
        district_or_town="Beitbridge", road_name=None,
        details=blank_details(traffic_disruption={
            "affected_road": "Beitbridge access road", "disruption_type": "closure",
            "affected_direction": None, "starts_on": "2026-11-05", "ends_on": None,
            "alternative_routes": None, "severity_or_duration": None,
        }),
    )
    base.update(overrides)
    return intel_reply(**base)
