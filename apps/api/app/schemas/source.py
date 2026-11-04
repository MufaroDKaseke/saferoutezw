"""Data-source and ingestion-run responses."""

from __future__ import annotations

import uuid

from app.models.enums import IngestionStatus, SourceKind, VerificationTier
from app.schemas.common import ApiModel, UtcDatetime


class SourceOut(ApiModel):
    id: uuid.UUID
    name: str
    kind: SourceKind
    feed_url: str | None
    enabled: bool
    poll_interval_seconds: int
    verification_tier: VerificationTier
    rights_notes: str | None
    last_polled_at: UtcDatetime | None
    last_success_at: UtcDatetime | None
    last_error: str | None
    error_count_7d: int
    article_count: int


class IngestionRunOut(ApiModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: str
    started_at: UtcDatetime
    completed_at: UtcDatetime | None
    status: IngestionStatus
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    error_count: int
    error_message: str | None
