"""Persist a classified extraction as an intelligence record (and its statistics).

Pure database mapping, no model calls. An intelligence record is never an incident; the pipeline
links one to an incident only when the taxonomy allows it (``may_create_incident``), and a CHECK
constraint backs that up.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models import ExtractionRun, SourceItem
from app.models.intelligence import IntelligenceRecord, StatisticalObservation
from app.schemas.intelligence import IntelligenceExtraction
from app.taxonomy import TAXONOMY_VERSION, PrimaryCategory, RecordStatus

_WORDS = re.compile(r"[a-z0-9]+")


def _slug(*parts: str | None) -> str:
    words: list[str] = []
    for part in parts:
        if part:
            words.extend(_WORDS.findall(part.lower()))
    return "-".join(words)[:120]


def topic_key(extraction: IntelligenceExtraction) -> str | None:
    """A coarse key that groups follow-up coverage of one project, policy or report.

    It links records; it never merges or discards them, and copies of one press release are
    not treated as independent corroboration. Returns None when there is nothing to anchor on.
    """
    block = extraction.category_details
    category = extraction.primary_category
    key = ""
    if category is PrimaryCategory.ROAD_INFRASTRUCTURE and block is not None:
        key = _slug(block.project_name or block.road_segment)  # type: ignore[attr-defined]
    elif category is PrimaryCategory.TRANSPORT_POLICY and block is not None:
        key = _slug(block.policy_or_regulation, block.responsible_institution)  # type: ignore[attr-defined]
    elif category is PrimaryCategory.ROAD_SAFETY_DATA and block is not None:
        key = _slug(block.source_of_statistics, block.reporting_period)  # type: ignore[attr-defined]
    elif category is PrimaryCategory.ROAD_SAFETY and block is not None:
        key = _slug(block.organisation, block.initiative_type)  # type: ignore[attr-defined]
    return f"{category.value}:{key}" if key else None


def quality_payload(extraction: IntelligenceExtraction) -> dict[str, Any]:
    return {
        "flags": [f.value for f in extraction.data_quality_flags],
        "missing_information": list(extraction.missing_information),
        "evidence": list(extraction.evidence_references),
        "other_explanation": extraction.other_explanation,
        "temporal_status_note": "AI-proposed; recent publication does not imply ongoing",
        "ai_candidate": True,
    }


def store_intelligence(
    db: Session,
    item: SourceItem,
    run: ExtractionRun,
    extraction: IntelligenceExtraction,
    *,
    extraction_version: str,
) -> IntelligenceRecord:
    """Insert the candidate record and its statistical observations in the caller's transaction."""
    record = IntelligenceRecord(
        source_item_id=item.id,
        extraction_run_id=run.id,
        extraction_version=extraction_version,
        taxonomy_version=TAXONOMY_VERSION,
        primary_category=extraction.primary_category.value,
        primary_subtype=extraction.primary_subtype.value if extraction.primary_subtype else None,
        secondary_categories=[c.value for c in extraction.secondary_categories],
        record_kind=extraction.record_kind.value,
        temporal_status=extraction.temporal_status.value,
        geographic_scope=extraction.geographic_scope.value,
        classification_confidence=extraction.classification_confidence,
        headline=extraction.short_headline.strip() or item.title_redacted,
        neutral_summary=extraction.neutral_summary.strip() or item.title_redacted,
        event_date=extraction.event_or_announcement_date,
        location_description=extraction.location_description,
        country=extraction.country,
        province=extraction.province_or_region,
        district_or_town=extraction.district_or_town,
        road_name=extraction.road_name,
        source_attribution=extraction.source_attribution,
        topic_key=topic_key(extraction),
        details=extraction.details_json(),
        quality=quality_payload(extraction),
        needs_editorial_review=extraction.needs_editorial_review,
        status=RecordStatus.CANDIDATE.value,
    )
    db.add(record)
    db.flush()
    for stat in extraction.statistics:
        db.add(
            StatisticalObservation(
                record_id=record.id,
                metric=stat.metric,
                value=Decimal(str(stat.value)),
                unit=stat.unit,
                period_start=stat.period_start,
                period_end=stat.period_end,
                geographic_coverage=stat.geographic_coverage,
                source_reference=stat.source_reference,
                methodology=stat.methodology,
                comparison_period=stat.comparison_period,
                is_preliminary=stat.is_preliminary,
            )
        )
    db.flush()
    return record
