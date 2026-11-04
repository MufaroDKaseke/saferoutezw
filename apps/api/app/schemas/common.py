"""Building blocks shared by every response model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer, WithJsonSchema


def _utc_iso(value: datetime) -> str:
    """ISO 8601 in UTC with a trailing Z (naive values are taken to be UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[
    datetime,
    PlainSerializer(_utc_iso, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


class ApiModel(BaseModel):
    """Base for response models: built from attributes, never serialises ORM objects directly."""

    model_config = ConfigDict(from_attributes=True)
