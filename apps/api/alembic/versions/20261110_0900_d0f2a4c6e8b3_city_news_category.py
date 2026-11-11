"""city_news primary category (Bulawayo / NUST deployment)

Revision ID: d0f2a4c6e8b3
Revises: c9e1f3a5b7d2
Create Date: 2026-11-10 09:00:00.000000

Additive: widens the taxonomy CHECK constraints on ``intelligence_records`` and
``intelligence_versions`` so a record can be classified ``city_news`` (civic and campus news that
is not about transport). No data is changed. The existing constraint
``only_actionable_events_link_incidents`` is untouched, so city news can never create an incident.

The category lists are written out literally (not imported from the application) so this revision
keeps meaning what it meant when it was written, even if the taxonomy changes later.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d0f2a4c6e8b3"
down_revision: Union[str, Sequence[str], None] = "c9e1f3a5b7d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BASE_SUBTYPES = {
    "road_incident": ("collision", "head_on_collision", "rear_end_collision", "multi_vehicle_collision",
                      "vehicle_rollover", "pedestrian_collision", "cyclist_collision", "hit_and_run",
                      "vehicle_fire", "vehicle_off_road", "other_road_accident"),
    "traffic_disruption": ("traffic_congestion", "road_closure", "lane_closure", "traffic_diversion",
                           "road_blockage", "vehicle_breakdown", "abnormal_delay", "border_queue",
                           "tollgate_congestion", "other_traffic_disruption"),
    "road_hazard": ("pothole", "road_surface_damage", "flooded_road", "washed_away_road", "bridge_damage",
                    "landslide_or_rockfall", "fallen_tree", "debris_on_road", "unsafe_roadworks",
                    "poor_visibility", "other_road_hazard"),
    "road_infrastructure": ("road_rehabilitation", "road_construction", "bridge_construction",
                            "bridge_rehabilitation", "scheduled_roadworks", "infrastructure_project",
                            "tollgate_infrastructure", "road_network_upgrade", "infrastructure_funding",
                            "other_road_infrastructure"),
    "public_transport": ("bus_service_change", "kombi_service_change", "route_change", "fare_change",
                         "service_disruption", "operator_announcement", "passenger_safety",
                         "fleet_development", "public_transport_regulation", "other_public_transport"),
    "freight_and_logistics": ("border_post_delay", "freight_restriction", "haulage_disruption",
                              "truck_queue", "logistics_policy", "freight_route_change",
                              "cross_border_transport", "other_freight_logistics"),
    "road_safety": ("road_safety_campaign", "traffic_enforcement", "speed_enforcement",
                    "drunk_driving_enforcement", "vehicle_roadworthiness", "driver_licensing",
                    "safety_training", "safety_recommendations", "other_road_safety"),
    "road_safety_data": ("accident_statistics", "fatality_statistics", "injury_statistics",
                         "blackspot_analysis", "traffic_volume_statistics", "transport_research",
                         "annual_report", "safety_trend_analysis", "other_road_safety_data"),
    "transport_policy": ("policy_announcement", "transport_legislation", "toll_fee_change",
                         "licensing_regulation", "vehicle_regulation", "enforcement_policy",
                         "transport_budget", "institutional_announcement", "other_transport_policy"),
    "other_transport_intelligence": ("other",),
}
CITY_NEWS_SUBTYPES = ("nust_news", "campus_life", "education", "city_council", "municipal_services",
                      "utilities_and_power", "health_and_safety", "local_events", "other_city_news")


def _quoted(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _constraints(with_city_news: bool) -> tuple[str, str, str]:
    subtypes = dict(BASE_SUBTYPES)
    if with_city_news:
        subtypes["city_news"] = CITY_NEWS_SUBTYPES
    category = f"primary_category IN ({_quoted(subtypes)})"
    all_subtypes = [s for subs in subtypes.values() for s in dict.fromkeys(subs)]
    subtype_valid = f"primary_subtype IS NULL OR primary_subtype IN ({_quoted(dict.fromkeys(all_subtypes))})"
    branches = " OR ".join(
        f"(primary_category = '{c}' AND primary_subtype IN ({_quoted(subs)}))" for c, subs in subtypes.items()
    )
    matches = f"primary_subtype IS NULL OR {branches}"
    return category, subtype_valid, matches


def _replace(with_city_news: bool) -> None:
    category, subtype_valid, matches = _constraints(with_city_news)
    for table in ("intelligence_records", "intelligence_versions"):
        op.drop_constraint(op.f(f"ck_{table}_primary_category_valid"), table, type_="check")
        op.drop_constraint(op.f(f"ck_{table}_subtype_matches_category"), table, type_="check")
        op.create_check_constraint(op.f(f"ck_{table}_primary_category_valid"), table, category)
        op.create_check_constraint(op.f(f"ck_{table}_subtype_matches_category"), table, matches)
    op.drop_constraint(op.f("ck_intelligence_records_primary_subtype_valid"), "intelligence_records", type_="check")
    op.create_check_constraint(op.f("ck_intelligence_records_primary_subtype_valid"), "intelligence_records", subtype_valid)


def upgrade() -> None:
    _replace(with_city_news=True)


def downgrade() -> None:
    # Fails (by design) if city_news rows exist: they must be removed or reclassified first.
    _replace(with_city_news=False)
