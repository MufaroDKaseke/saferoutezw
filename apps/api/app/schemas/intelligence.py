"""Unified structured output for transport-intelligence extraction.

One schema, one OpenAI call: common classification fields plus a ``details`` object with one
nullable block per primary category (only the matching block is filled). Everything the model
returns is an *unverified candidate*; humans review it. Fields are required-but-nullable so the
JSON schema works with Structured Outputs strict mode, and every value is validated again here
because the model is not trusted.

Rules enforced in code, not left to the prompt:
  * the subtype must belong to the primary category (otherwise it is dropped and flagged),
  * only an actionable category with record_kind=actionable_event can ever produce an incident
    (``app.taxonomy.may_create_incident``); statistics, policy and projects never do.
"""

from __future__ import annotations

import math
from datetime import date, time
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import IncidentType, Severity
from app.schemas.extraction import ExtractionResult
from app.taxonomy import (
    ACTIONABLE_CATEGORIES,
    ALL_SUBTYPES,
    GeographicScope,
    PrimaryCategory,
    RecordKind,
    TemporalStatus,
    is_valid_subtype,
    may_create_incident,
)

Subtype = StrEnum("Subtype", {s.upper(): s for s in ALL_SUBTYPES})


class DataQualityFlag(StrEnum):
    FIGURES_UNVERIFIED = "figures_unverified"
    PRELIMINARY_FIGURES = "preliminary_figures"
    LOCATION_UNCERTAIN = "location_uncertain"
    DATE_UNCERTAIN = "date_uncertain"
    UNCLEAR_IF_ONGOING = "unclear_if_ongoing"
    SECOND_HAND_REPORT = "second_hand_report"
    OPINION_OR_COMMENTARY = "opinion_or_commentary"
    CONFLICTING_FIGURES = "conflicting_figures"
    NO_ZIMBABWE_LINK = "no_zimbabwe_link"
    # Set by validation, never by the model:
    SUBTYPE_MISMATCH = "subtype_mismatch"
    KIND_ADJUSTED = "kind_adjusted"
    MISSING_EXPLANATION = "missing_explanation"


class _Block(BaseModel):
    """Base for payload blocks: strict keys, blank strings become null."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: (None if isinstance(v, str) and not v.strip() else v) for k, v in data.items()}
        return data


class MoneyAmount(_Block):
    description: str = Field(description="What the amount is for, as stated (e.g. 'bus fare Harare-Mutare').")
    amount: float | None = Field(description="Number as stated, or null.")
    currency: str | None = Field(description="Currency as stated (USD, ZiG, ZWL, ZAR...), or null.")


class RoadIncidentDetails(_Block):
    severity: Severity
    vehicle_types: list[str] = Field(description="Vehicle kinds stated (kombi, haulage truck...). Empty if none.")
    vehicles_involved: int | None = Field(description="Count only if stated.")
    road_users: list[str] = Field(description="Road user groups stated (passengers, pedestrians, cyclists...).")
    fatalities: int | None = Field(description="Reported deaths, only if stated.")
    injuries: int | None = Field(description="Reported injuries, only if stated.")
    crash_mechanism: str | None = Field(description="Stated cause or mechanism (overturned, head-on...).")
    road_obstruction: bool | None = Field(description="Whether the article says the road was blocked.")
    emergency_response: str | None = Field(description="Stated emergency or police response.")
    occurred_time: time | None = Field(description="HH:MM Zimbabwe local time, only if stated.")


class TrafficDisruptionDetails(_Block):
    affected_road: str | None
    disruption_type: str | None = Field(description="Closure, diversion, queue, congestion... as stated.")
    affected_direction: str | None
    starts_on: date | None
    ends_on: date | None
    alternative_routes: str | None = Field(description="Only routes an official source recommends.")
    severity_or_duration: str | None = Field(description="Only if stated, e.g. 'queue of 5km'.")


class RoadHazardDetails(_Block):
    hazard_type: str | None
    road_segment: str | None
    reported_condition: str | None
    traffic_effect: str | None
    starts_on: date | None
    ends_on: date | None


class RoadInfrastructureDetails(_Block):
    project_name: str | None
    road_segment: str | None
    project_type: str | None
    project_status: str | None = Field(description="Announced, ongoing, completed... as stated.")
    cost_amount: float | None
    cost_currency: str | None
    contractor: str | None
    timeline: str | None
    traffic_disruption_confirmed: bool | None = Field(
        description="True only if the article separately confirms closures or diversions."
    )


class PublicTransportDetails(_Block):
    operator: str | None
    service_or_route: str | None
    fare_changes: list[MoneyAmount]
    effective_date: date | None
    affected_passengers_or_services: str | None


class FreightDetails(_Block):
    border_post: str | None
    corridor: str | None
    restriction_type: str | None
    queue_or_delay: str | None = Field(description="Only if explicitly stated, with units.")
    vehicle_class: str | None


class RoadSafetyDetails(_Block):
    organisation: str | None
    initiative_type: str | None
    target_population: str | None
    announced_dates: str | None
    measures: str | None = Field(description="Enforcement or educational measures stated.")


class RoadSafetyDataDetails(_Block):
    reporting_period: str | None
    geographic_coverage: str | None
    indicator_names: list[str]
    source_of_statistics: str | None
    methodology: str | None
    comparison_period: str | None
    is_preliminary: bool | None
    contains_historical_dataset: bool | None


class TransportPolicyDetails(_Block):
    responsible_institution: str | None
    policy_or_regulation: str | None
    announcement_date: date | None
    effective_date: date | None
    affected_parties: str | None
    obligations: str | None
    amounts: list[MoneyAmount]


class Details(_Block):
    """Fill only the block for ``primary_category``; leave the others null."""

    road_incident: RoadIncidentDetails | None
    traffic_disruption: TrafficDisruptionDetails | None
    road_hazard: RoadHazardDetails | None
    road_infrastructure: RoadInfrastructureDetails | None
    public_transport: PublicTransportDetails | None
    freight_and_logistics: FreightDetails | None
    road_safety: RoadSafetyDetails | None
    road_safety_data: RoadSafetyDataDetails | None
    transport_policy: TransportPolicyDetails | None


class StatisticalObservation(_Block):
    """One reported figure. Never summed with others that have another period or definition."""

    metric: str = Field(description="What is counted, as named in the source (e.g. 'road deaths').")
    value: float
    unit: str = Field(description="Unit as stated (persons, crashes, vehicles, %, USD...).")
    period_start: date | None
    period_end: date | None
    geographic_coverage: str | None
    source_reference: str | None = Field(description="Institution or report the figure is attributed to.")
    methodology: str | None
    comparison_period: str | None
    is_preliminary: bool | None

    @field_validator("value")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value

    @model_validator(mode="after")
    def _period_order(self) -> StatisticalObservation:
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("period_end is before period_start")
        return self


class IntelligenceExtraction(_Block):
    """What the model says about one article. All of it is an unverified candidate."""

    is_transport_relevant: bool = Field(
        description="False for anything not about Zimbabwean roads/transport (or with no Zimbabwe link)."
    )
    primary_category: PrimaryCategory
    primary_subtype: Subtype | None = Field(description="Only when the text supports one; otherwise null.")
    secondary_categories: list[PrimaryCategory] = Field(max_length=3)
    record_kind: RecordKind
    temporal_status: TemporalStatus = Field(
        description="Only meaningful for actionable events. Publication recency does not mean ongoing."
    )
    geographic_scope: GeographicScope
    classification_confidence: float = Field(ge=0, le=1)
    other_explanation: str | None = Field(
        description="Required when primary_category is other_transport_intelligence."
    )
    short_headline: str = Field(max_length=200)
    neutral_summary: str = Field(max_length=1200, description="Neutral 1-3 sentences. No private names.")
    event_or_announcement_date: date | None = Field(description="YYYY-MM-DD, Zimbabwe local, only if stated.")
    location_description: str | None = Field(max_length=300)
    country: str | None
    province_or_region: str | None
    district_or_town: str | None
    road_name: str | None
    nearest_landmark: str | None
    source_attribution: str | None = Field(description="Institution the article attributes its facts to.")
    evidence_references: list[str] = Field(max_length=5, description="Short verbatim quotes.")
    data_quality_flags: list[DataQualityFlag]
    missing_information: list[str] = Field(max_length=10)
    needs_editorial_review: bool
    details: Details
    statistics: list[StatisticalObservation] = Field(max_length=40)

    @model_validator(mode="after")
    def _enforce_taxonomy_rules(self) -> IntelligenceExtraction:
        flags = list(self.data_quality_flags)

        def flag(f: DataQualityFlag) -> None:
            if f not in flags:
                flags.append(f)

        if self.primary_subtype is not None and not is_valid_subtype(
            self.primary_category.value, self.primary_subtype.value
        ):
            self.primary_subtype = None
            flag(DataQualityFlag.SUBTYPE_MISMATCH)

        category = self.primary_category
        if self.record_kind is RecordKind.ACTIONABLE_EVENT and category not in ACTIONABLE_CATEGORIES:
            self.record_kind = (
                RecordKind.STATISTICAL_REPORT
                if category is PrimaryCategory.ROAD_SAFETY_DATA
                else RecordKind.INFORMATIONAL_DEVELOPMENT
            )
            flag(DataQualityFlag.KIND_ADJUSTED)

        if category is PrimaryCategory.OTHER_TRANSPORT_INTELLIGENCE and not self.other_explanation:
            flag(DataQualityFlag.MISSING_EXPLANATION)
            self.needs_editorial_review = True

        self.secondary_categories = [c for c in dict.fromkeys(self.secondary_categories) if c != category]
        self.data_quality_flags = flags
        return self

    # -- derived views ---------------------------------------------------------------
    @property
    def category_details(self) -> BaseModel | None:
        return getattr(self.details, self.primary_category.value, None)

    @property
    def creates_incident(self) -> bool:
        return self.is_transport_relevant and may_create_incident(
            self.primary_category.value, self.record_kind.value
        )

    def details_json(self) -> dict[str, Any]:
        block = self.category_details
        return block.model_dump(mode="json") if block is not None else {}

    def to_legacy_result(self) -> ExtractionResult:
        """The incident-shaped view the existing pipeline consumes.

        ``is_road_incident`` is true only when the taxonomy allows an incident row, so
        statistics, policy and infrastructure announcements can never become incidents.
        """
        block = self.category_details
        incident = block if isinstance(block, RoadIncidentDetails) else None
        fatalities = incident.fatalities if incident else None
        severity = incident.severity if incident else Severity.UNKNOWN
        if fatalities:
            severity = Severity.FATAL
        place = self.location_description or ", ".join(
            p for p in (self.road_name, self.district_or_town) if p
        ) or None
        return ExtractionResult(
            is_road_incident=self.creates_incident,
            confidence=self.classification_confidence,
            incident_type=_incident_type(self),
            severity=severity,
            location_text=place[:300] if place else None,
            occurred_on=self.event_or_announcement_date,
            occurred_time=incident.occurred_time if incident else None,
            fatalities=fatalities,
            injuries=incident.injuries if incident else None,
            vehicles_involved=incident.vehicles_involved if incident else None,
            cause=(incident.crash_mechanism[:500] if incident and incident.crash_mechanism else None),
            summary=self.neutral_summary,
            evidence_quotes=self.evidence_references[:5],
        )


_SUBTYPE_TO_INCIDENT_TYPE = {
    "pedestrian_collision": IncidentType.PEDESTRIAN_STRIKE,
    "cyclist_collision": IncidentType.PEDESTRIAN_STRIKE,
    "vehicle_rollover": IncidentType.ROLLOVER,
    "vehicle_fire": IncidentType.VEHICLE_FIRE,
    "vehicle_breakdown": IncidentType.BREAKDOWN,
    "road_closure": IncidentType.ROAD_CLOSURE,
    "lane_closure": IncidentType.ROAD_CLOSURE,
    "traffic_diversion": IncidentType.ROAD_CLOSURE,
    "road_blockage": IncidentType.ROAD_CLOSURE,
    "vehicle_off_road": IncidentType.OTHER,
}
_COLLISIONS = {"collision", "head_on_collision", "rear_end_collision", "multi_vehicle_collision", "hit_and_run"}


def _incident_type(extraction: IntelligenceExtraction) -> IncidentType:
    subtype = extraction.primary_subtype.value if extraction.primary_subtype else None
    if subtype in _COLLISIONS:
        return IncidentType.COLLISION
    if subtype in _SUBTYPE_TO_INCIDENT_TYPE:
        return _SUBTYPE_TO_INCIDENT_TYPE[subtype]
    category = extraction.primary_category
    if category is PrimaryCategory.ROAD_HAZARD:
        return IncidentType.ROAD_HAZARD
    if category is PrimaryCategory.TRAFFIC_DISRUPTION:
        return IncidentType.TRAFFIC_DISRUPTION
    return IncidentType.OTHER


# --------------------------------------------------------------------------- JSON schema

_STRIPPED = {"title", "default", "maxLength", "minLength", "minimum", "maximum", "maxItems", "minItems"}


def _strictify(node: Any) -> Any:
    """Make a Pydantic JSON schema acceptable to Structured Outputs strict mode."""
    if isinstance(node, dict):
        out = {k: _strictify(v) for k, v in node.items() if k not in _STRIPPED or k == "properties"}
        if "$ref" in out:
            # Pydantic emits {"$ref": ..., "description": ...} for an enum/model field with a
            # description; strict mode rejects any keyword beside $ref, so keep only the ref.
            return {"$ref": out["$ref"]}
        if out.get("type") == "object" and "properties" in out:
            out["required"] = list(out["properties"])
            out["additionalProperties"] = False
        return out
    if isinstance(node, list):
        return [_strictify(v) for v in node]
    return node


def build_json_schema() -> dict[str, Any]:
    return _strictify(IntelligenceExtraction.model_json_schema())


INTELLIGENCE_JSON_SCHEMA: dict[str, Any] = build_json_schema()
