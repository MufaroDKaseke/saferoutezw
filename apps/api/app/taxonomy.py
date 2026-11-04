"""Central, versioned transport-intelligence taxonomy.

One definition shared by keyword screening, AI extraction, database CHECK constraints,
APIs and (via ``scripts/export_taxonomy.py``) the web app. Values are stable machine
strings; never build categories from free model text.

Three concepts are kept apart on purpose:
  * the *category* of a source item (what it is about),
  * its *record kind* (actionable event vs. report vs. announcement ...),
  * its *temporal status* (only meaningful for actionable events).
A category never implies that a road situation is currently active.
"""

from __future__ import annotations

from enum import StrEnum

TAXONOMY_VERSION = "2026.11.1"


class PrimaryCategory(StrEnum):
    ROAD_INCIDENT = "road_incident"
    TRAFFIC_DISRUPTION = "traffic_disruption"
    ROAD_HAZARD = "road_hazard"
    ROAD_INFRASTRUCTURE = "road_infrastructure"
    PUBLIC_TRANSPORT = "public_transport"
    FREIGHT_AND_LOGISTICS = "freight_and_logistics"
    ROAD_SAFETY = "road_safety"
    ROAD_SAFETY_DATA = "road_safety_data"
    TRANSPORT_POLICY = "transport_policy"
    OTHER_TRANSPORT_INTELLIGENCE = "other_transport_intelligence"


class RecordKind(StrEnum):
    ACTIONABLE_EVENT = "actionable_event"
    INFORMATIONAL_DEVELOPMENT = "informational_development"
    STATISTICAL_REPORT = "statistical_report"
    RESEARCH_OR_ANALYSIS = "research_or_analysis"
    ADVISORY = "advisory"
    UNKNOWN = "unknown"


class TemporalStatus(StrEnum):
    PLANNED = "planned"
    ONGOING = "ongoing"
    RESOLVED = "resolved"
    HISTORICAL = "historical"
    UNKNOWN = "unknown"


class GeographicScope(StrEnum):
    PRECISE_POINT = "precise_point"
    APPROXIMATE_POINT = "approximate_point"
    ROAD_SEGMENT = "road_segment"
    CORRIDOR = "corridor"
    TOWN = "town"
    DISTRICT = "district"
    PROVINCE = "province"
    NATIONAL = "national"
    REGIONAL = "regional"
    UNKNOWN = "unknown"


class RecordStatus(StrEnum):
    """Editorial status of an intelligence record (mirrors IncidentStatus)."""

    CANDIDATE = "candidate"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PublicationOutput(StrEnum):
    """What an approved non-incident record may become. Never a hazard alert."""

    TRANSPORT_NEWS = "transport_news"
    STATISTICAL_INSIGHT = "statistical_insight"
    ANALYTICAL_REPORT = "analytical_report"
    JOURNALISM_BRIEFING = "journalism_briefing"
    DASHBOARD_SOURCE = "dashboard_source"


SUBTYPES: dict[PrimaryCategory, tuple[str, ...]] = {
    PrimaryCategory.ROAD_INCIDENT: (
        "collision", "head_on_collision", "rear_end_collision", "multi_vehicle_collision",
        "vehicle_rollover", "pedestrian_collision", "cyclist_collision", "hit_and_run",
        "vehicle_fire", "vehicle_off_road", "other_road_accident",
    ),
    PrimaryCategory.TRAFFIC_DISRUPTION: (
        "traffic_congestion", "road_closure", "lane_closure", "traffic_diversion",
        "road_blockage", "vehicle_breakdown", "abnormal_delay", "border_queue",
        "tollgate_congestion", "other_traffic_disruption",
    ),
    PrimaryCategory.ROAD_HAZARD: (
        "pothole", "road_surface_damage", "flooded_road", "washed_away_road", "bridge_damage",
        "landslide_or_rockfall", "fallen_tree", "debris_on_road", "unsafe_roadworks",
        "poor_visibility", "other_road_hazard",
    ),
    PrimaryCategory.ROAD_INFRASTRUCTURE: (
        "road_rehabilitation", "road_construction", "bridge_construction",
        "bridge_rehabilitation", "scheduled_roadworks", "infrastructure_project",
        "tollgate_infrastructure", "road_network_upgrade", "infrastructure_funding",
        "other_road_infrastructure",
    ),
    PrimaryCategory.PUBLIC_TRANSPORT: (
        "bus_service_change", "kombi_service_change", "route_change", "fare_change",
        "service_disruption", "operator_announcement", "passenger_safety", "fleet_development",
        "public_transport_regulation", "other_public_transport",
    ),
    PrimaryCategory.FREIGHT_AND_LOGISTICS: (
        "border_post_delay", "freight_restriction", "haulage_disruption", "truck_queue",
        "logistics_policy", "freight_route_change", "cross_border_transport",
        "other_freight_logistics",
    ),
    PrimaryCategory.ROAD_SAFETY: (
        "road_safety_campaign", "traffic_enforcement", "speed_enforcement",
        "drunk_driving_enforcement", "vehicle_roadworthiness", "driver_licensing",
        "safety_training", "safety_recommendations", "other_road_safety",
    ),
    PrimaryCategory.ROAD_SAFETY_DATA: (
        "accident_statistics", "fatality_statistics", "injury_statistics", "blackspot_analysis",
        "traffic_volume_statistics", "transport_research", "annual_report",
        "safety_trend_analysis", "other_road_safety_data",
    ),
    PrimaryCategory.TRANSPORT_POLICY: (
        "policy_announcement", "transport_legislation", "toll_fee_change", "licensing_regulation",
        "vehicle_regulation", "enforcement_policy", "transport_budget",
        "institutional_announcement", "other_transport_policy",
    ),
    # No fixed subtypes: the explanation lives in the record's quality notes.
    PrimaryCategory.OTHER_TRANSPORT_INTELLIGENCE: ("other",),
}

ALL_SUBTYPES: tuple[str, ...] = tuple(dict.fromkeys(s for subs in SUBTYPES.values() for s in subs))

CATEGORY_LABELS: dict[str, str] = {
    "road_incident": "Road incidents",
    "traffic_disruption": "Traffic",
    "road_hazard": "Road hazards",
    "road_infrastructure": "Infrastructure",
    "public_transport": "Public transport",
    "freight_and_logistics": "Freight and logistics",
    "road_safety": "Road safety",
    "road_safety_data": "Road safety data",
    "transport_policy": "Transport policy",
    "other_transport_intelligence": "Other transport intelligence",
}

RECORD_KIND_LABELS: dict[str, str] = {
    "actionable_event": "Actionable event",
    "informational_development": "Informational development",
    "statistical_report": "Statistical report",
    "research_or_analysis": "Research or analysis",
    "advisory": "Advisory",
    "unknown": "Unknown",
}


def subtype_label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def is_valid_subtype(category: str, subtype: str) -> bool:
    try:
        return subtype in SUBTYPES[PrimaryCategory(category)]
    except ValueError:
        return False


# Categories whose items can describe a specific, location- and time-bound occurrence.
# Only these may ever produce an incident row, and only when record_kind is actionable_event.
ACTIONABLE_CATEGORIES: frozenset[PrimaryCategory] = frozenset(
    {PrimaryCategory.ROAD_INCIDENT, PrimaryCategory.TRAFFIC_DISRUPTION, PrimaryCategory.ROAD_HAZARD}
)

# Record kinds that can never produce a live road marker.
NON_ACTIONABLE_KINDS: frozenset[RecordKind] = frozenset(
    {RecordKind.STATISTICAL_REPORT, RecordKind.RESEARCH_OR_ANALYSIS,
     RecordKind.INFORMATIONAL_DEVELOPMENT}
)


def may_create_incident(category: str, record_kind: str) -> bool:
    """The single rule that keeps policy, statistics and projects out of ``incidents``."""
    try:
        return (
            PrimaryCategory(category) in ACTIONABLE_CATEGORIES
            and RecordKind(record_kind) is RecordKind.ACTIONABLE_EVENT
        )
    except ValueError:
        return False


# Which publication outputs an approved record may take. None of these is a hazard alert.
_ALL_NEWS = (PublicationOutput.TRANSPORT_NEWS, PublicationOutput.JOURNALISM_BRIEFING,
             PublicationOutput.DASHBOARD_SOURCE)
ALLOWED_OUTPUTS: dict[PrimaryCategory, tuple[PublicationOutput, ...]] = {
    c: _ALL_NEWS for c in PrimaryCategory
}
ALLOWED_OUTPUTS[PrimaryCategory.ROAD_SAFETY_DATA] = (
    *_ALL_NEWS, PublicationOutput.STATISTICAL_INSIGHT, PublicationOutput.ANALYTICAL_REPORT)
for _c in (PrimaryCategory.TRANSPORT_POLICY, PrimaryCategory.ROAD_INFRASTRUCTURE,
           PrimaryCategory.ROAD_SAFETY, PrimaryCategory.PUBLIC_TRANSPORT,
           PrimaryCategory.FREIGHT_AND_LOGISTICS):
    ALLOWED_OUTPUTS[_c] = (*_ALL_NEWS, PublicationOutput.ANALYTICAL_REPORT)


def output_allowed(category: str, output: str) -> bool:
    try:
        return PublicationOutput(output) in ALLOWED_OUTPUTS[PrimaryCategory(category)]
    except ValueError:
        return False


def subtype_category_check_sql(category_col: str, subtype_col: str) -> str:
    """CHECK text: a subtype, when present, must belong to its category."""
    branches = " OR ".join(
        f"({category_col} = '{c.value}' AND {subtype_col} IN ({', '.join(repr(s) for s in subs)}))"
        for c, subs in SUBTYPES.items()
    )
    return f"{subtype_col} IS NULL OR {branches}"


def taxonomy_as_dict() -> dict[str, object]:
    """JSON-serialisable view used by the export script and the drift test."""
    return {
        "version": TAXONOMY_VERSION,
        "categories": [c.value for c in PrimaryCategory],
        "category_labels": CATEGORY_LABELS,
        "subtypes": {c.value: list(s) for c, s in SUBTYPES.items()},
        "record_kinds": [k.value for k in RecordKind],
        "record_kind_labels": RECORD_KIND_LABELS,
        "temporal_statuses": [t.value for t in TemporalStatus],
        "geographic_scopes": [g.value for g in GeographicScope],
        "record_statuses": [s.value for s in RecordStatus],
        "publication_outputs": [o.value for o in PublicationOutput],
    }
