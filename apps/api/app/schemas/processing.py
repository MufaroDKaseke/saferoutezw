"""Processing history: source ingestion runs and AI extraction runs in one timeline."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from app.schemas.common import ApiModel, UtcDatetime

RunKind = Literal["ingestion", "extraction"]


class ProcessingRun(ApiModel):
    id: uuid.UUID
    kind: RunKind
    status: str
    started_at: UtcDatetime
    completed_at: UtcDatetime | None
    source_id: uuid.UUID | None
    source_name: str | None
    source_item_id: uuid.UUID | None
    headline: str | None
    model_name: str | None
    prompt_version: str | None
    extraction_confidence: float | None
    input_tokens: int | None
    output_tokens: int | None
    fetched_count: int | None
    inserted_count: int | None
    duplicate_count: int | None
    error_count: int | None
    error_message: str | None


class ProcessingRunDetail(ProcessingRun):
    """Adds the structured model output. The prompt and the article text are never exposed."""

    output: dict[str, Any] | None
