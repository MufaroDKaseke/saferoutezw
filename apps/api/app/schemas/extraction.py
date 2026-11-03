"""Structured output the AI must return for one article, and its validation.

The JSON schema sent to OpenAI (``EXTRACTION_JSON_SCHEMA``) uses Structured Outputs
strict mode: every property is required and nullable where it may be unknown. The
same data is then validated again with Pydantic, because the model is not trusted.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import IncidentType, Severity

HARARE = timezone(timedelta(hours=2), "CAT")  # Zimbabwe has no daylight saving


class ExtractionResult(BaseModel):
    """What the model says about an article. ``confidence`` is not proof of anything."""

    model_config = ConfigDict(extra="forbid")

    is_road_incident: bool
    confidence: float = Field(ge=0, le=1)
    incident_type: IncidentType
    severity: Severity
    location_text: str | None = Field(default=None, max_length=300)
    occurred_on: date | None = None
    occurred_time: time | None = None
    fatalities: int | None = Field(default=None, ge=0, le=1000)
    injuries: int | None = Field(default=None, ge=0, le=1000)
    vehicles_involved: int | None = Field(default=None, ge=0, le=500)
    cause: str | None = Field(default=None, max_length=500)
    summary: str = Field(max_length=1200)
    evidence_quotes: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("location_text", "cause", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("occurred_time", "occurred_on", mode="before")
    @classmethod
    def _blank_time_or_date(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    def occurred_at(self, published: datetime | None) -> datetime | None:
        """Best timestamp for the incident, in UTC, or None.

        A date later than the article's publication day (plus one day of slack) is
        a model error, not a prediction, so it is dropped.
        """
        if self.occurred_on is None:
            return None
        if published is not None and self.occurred_on > (published + timedelta(days=1)).date():
            return None
        moment = datetime.combine(self.occurred_on, self.occurred_time or time(0, 0), tzinfo=HARARE)
        return moment.astimezone(timezone.utc)


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "is_road_incident", "confidence", "incident_type", "severity", "location_text",
        "occurred_on", "occurred_time", "fatalities", "injuries", "vehicles_involved",
        "cause", "summary", "evidence_quotes",
    ],
    "properties": {
        "is_road_incident": {
            "type": "boolean",
            "description": "True only if the article reports a specific road traffic incident "
            "(crash, collision, rollover, pedestrian strike, vehicle fire, breakdown or road hazard).",
        },
        "confidence": {"type": "number", "description": "0 to 1: how sure you are of this classification."},
        "incident_type": {"type": "string", "enum": [t.value for t in IncidentType]},
        "severity": {"type": "string", "enum": [s.value for s in Severity]},
        "location_text": _nullable({"type": "string"}),
        "occurred_on": _nullable({"type": "string", "description": "YYYY-MM-DD in Zimbabwe local time."}),
        "occurred_time": _nullable({"type": "string", "description": "HH:MM 24-hour, Zimbabwe local time."}),
        "fatalities": _nullable({"type": "integer"}),
        "injuries": _nullable({"type": "integer"}),
        "vehicles_involved": _nullable({"type": "integer"}),
        "cause": _nullable({"type": "string"}),
        "summary": {"type": "string", "description": "Neutral 1-3 sentence summary. No names of private people."},
        "evidence_quotes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Up to 3 short verbatim quotes from the article that support the classification.",
        },
    },
}
