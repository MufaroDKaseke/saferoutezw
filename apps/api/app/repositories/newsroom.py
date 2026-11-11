"""Newsroom queries: articles as a journalist sees them, with their general-news classification.

Classification lives on ``source_items.source_metadata["classification"]`` (written by the pipeline in
newsroom mode) and the full model output on ``extraction_runs``; nothing here needs a table of its own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, Select, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import ExtractionRun, Source, SourceItem
from app.models.enums import ExtractionStatus, ProcessingStatus
from app.repositories.incidents import _like
from app.repositories.sources import build_sources
from app.schemas.newsroom import NEWS_CATEGORY_LABELS
from app.schemas.newsroom_api import (
    ArticleDetail,
    ArticleReview,
    ArticleSummary,
    CountBy,
    FeedHealth,
    NewsroomSummary,
    PublisherCount,
    UsageToday,
)

HARARE = ZoneInfo("Africa/Harare")
PENDING_STATUSES = (
    ProcessingStatus.PENDING.value,
    ProcessingStatus.SCREENED.value,
    ProcessingStatus.FETCHED.value,
    ProcessingStatus.PROCESSING.value,
)
FAILED_STATUSES = (ProcessingStatus.FAILED.value, ProcessingStatus.FETCH_FAILED.value)
SKIPPED_STATUSES = (ProcessingStatus.FILTERED.value, ProcessingStatus.DISCARDED.value)

_CLASSIFICATION = SourceItem.source_metadata["classification"]
_REVIEW = SourceItem.source_metadata["newsroom_review"]


def _has_classification():
    return SourceItem.source_metadata.has_key("classification")


@dataclass
class ArticleFilters:
    q: str | None = None
    source_id: uuid.UUID | None = None
    category: str | None = None
    state: str | None = None
    review_status: str | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None
    collected_from: datetime | None = None
    collected_to: datetime | None = None
    sort: str = "collected_at"
    descending: bool = True


def articles_query(f: ArticleFilters) -> Select:
    query = select(SourceItem, Source.name).join(Source, Source.id == SourceItem.source_id)
    if f.q and f.q.strip():
        like = _like(f.q.strip())
        query = query.where(
            or_(
                SourceItem.title_redacted.ilike(like),
                SourceItem.excerpt_redacted.ilike(like),
                SourceItem.article_text_redacted.ilike(like),
                _CLASSIFICATION["summary"].as_string().ilike(like),
            )
        )
    if f.source_id:
        query = query.where(SourceItem.source_id == f.source_id)
    if f.category:
        query = query.where(
            or_(
                _CLASSIFICATION["primary_category"].as_string() == f.category,
                _CLASSIFICATION["secondary_category"].as_string() == f.category,
            )
        )
    if f.state == "classified":
        query = query.where(SourceItem.processing_status == ProcessingStatus.PROCESSED.value, _has_classification())
    elif f.state == "pending":
        query = query.where(SourceItem.processing_status.in_(PENDING_STATUSES))
    elif f.state == "failed":
        query = query.where(SourceItem.processing_status.in_(FAILED_STATUSES))
    elif f.state == "skipped":
        query = query.where(SourceItem.processing_status.in_(SKIPPED_STATUSES))
    if f.review_status == "new":
        query = query.where(or_(~SourceItem.source_metadata.has_key("newsroom_review"), _REVIEW["status"].as_string() == "new"))
    elif f.review_status:
        query = query.where(_REVIEW["status"].as_string() == f.review_status)
    if f.published_from:
        query = query.where(SourceItem.published_at >= f.published_from)
    if f.published_to:
        query = query.where(SourceItem.published_at <= f.published_to)
    if f.collected_from:
        query = query.where(SourceItem.received_at >= f.collected_from)
    if f.collected_to:
        query = query.where(SourceItem.received_at <= f.collected_to)
    column = SourceItem.published_at if f.sort == "published_at" else SourceItem.received_at
    ordering = column.desc().nulls_last() if f.descending else column.asc().nulls_last()
    return query.order_by(ordering, SourceItem.id)


def article_state(item: SourceItem) -> str:
    status = item.processing_status
    if status == ProcessingStatus.PROCESSED.value and "classification" in (item.source_metadata or {}):
        return "classified"
    if status in FAILED_STATUSES:
        return "failed"
    if status in SKIPPED_STATUSES:
        return "skipped"
    return "pending"


def _review(item: SourceItem) -> ArticleReview:
    raw = (item.source_metadata or {}).get("newsroom_review") or {}
    at = raw.get("at")
    return ArticleReview(
        status=raw.get("status", "new"),
        by=raw.get("by"),
        at=datetime.fromisoformat(at) if at else None,
        note=raw.get("note"),
    )


def _summary_fields(item: SourceItem, source_name: str) -> dict[str, Any]:
    meta = item.source_metadata or {}
    cls = meta.get("classification") or {}
    return dict(
        id=item.id,
        publisher_id=item.source_id,
        publisher=source_name,
        headline=item.title_redacted,
        source_url=item.canonical_url or meta.get("url"),
        published_at=item.published_at,
        collected_at=item.received_at,
        state=article_state(item),
        processing_status=item.processing_status,
        category=cls.get("primary_category"),
        secondary_category=cls.get("secondary_category"),
        summary=cls.get("summary"),
        geographic_relevance=cls.get("geographic_relevance"),
        needs_editorial_attention=bool(cls.get("needs_editorial_attention", False)),
        classification_basis=cls.get("basis"),
        review=_review(item),
    )


def build_summaries(rows: list[Any]) -> list[ArticleSummary]:
    return [ArticleSummary(**_summary_fields(item, name)) for item, name in rows]


def get_detail(session: Session, article_id: uuid.UUID) -> ArticleDetail | None:
    row = session.execute(
        select(SourceItem, Source.name).join(Source, Source.id == SourceItem.source_id).where(SourceItem.id == article_id)
    ).first()
    if row is None:
        return None
    item, name = row
    cls = (item.source_metadata or {}).get("classification") or {}
    last_error = session.scalar(
        select(ExtractionRun.error_message)
        .where(ExtractionRun.source_item_id == item.id, ExtractionRun.status == ExtractionStatus.FAILED.value)
        .order_by(ExtractionRun.created_at.desc())
        .limit(1)
    )
    classified_at = cls.get("at")
    reused = cls.get("reused_from")
    return ArticleDetail(
        **_summary_fields(item, name),
        excerpt=item.excerpt_redacted,
        article_text=item.article_text_redacted,
        topics=cls.get("topics") or [],
        organisations=cls.get("organisations") or [],
        places=cls.get("places") or [],
        attention_reason=cls.get("attention_reason"),
        classification_confidence=cls.get("classification_confidence"),
        model=cls.get("model"),
        prompt_version=cls.get("prompt_version"),
        classified_at=datetime.fromisoformat(classified_at) if classified_at else None,
        reused_from=uuid.UUID(reused) if reused else None,
        fetch_error=item.fetch_error,
        last_error=last_error,
    )


def _today_start() -> datetime:
    local = datetime.now(HARARE)
    return datetime(local.year, local.month, local.day, tzinfo=HARARE).astimezone(UTC)


def feed_health(session: Session, settings: Settings) -> FeedHealth:
    """A feed is healthy when it is enabled and polled successfully recently (about 5 polling cycles)."""
    sources = list(session.scalars(select(Source).where(Source.kind == "rss")))
    if not sources:
        return FeedHealth(enabled=0, healthy=0, unhealthy=0, disabled=0)
    window = timedelta(seconds=max(900, settings.rss_poll_interval_seconds * 5))
    now = datetime.now(UTC)
    healthy = enabled = 0
    for out in build_sources(session, [s for s in sources if s.enabled]):
        enabled += 1
        if out.last_success_at and now - out.last_success_at <= window:
            healthy += 1
    return FeedHealth(
        enabled=enabled, healthy=healthy, unhealthy=enabled - healthy, disabled=sum(1 for s in sources if not s.enabled)
    )


def summary(session: Session, settings: Settings) -> NewsroomSummary:
    start = _today_start()
    count = lambda *where: session.scalar(select(func.count()).select_from(SourceItem).where(*where)) or 0  # noqa: E731
    classified_at = cast(_CLASSIFICATION["at"].as_string(), DateTime(timezone=True))
    usage = session.execute(
        select(
            func.coalesce(func.sum(ExtractionRun.input_tokens), 0),
            func.coalesce(func.sum(ExtractionRun.output_tokens), 0),
        ).where(
            ExtractionRun.status == ExtractionStatus.SUCCEEDED.value,
            ExtractionRun.prompt_version.like("newsroom%"),
            ExtractionRun.completed_at >= start,
        )
    ).one()
    tokens_in, tokens_out = int(usage[0]), int(usage[1])
    cost = None
    if settings.newsroom_price_input_per_1m is not None and settings.newsroom_price_output_per_1m is not None:
        cost = round(
            tokens_in / 1e6 * settings.newsroom_price_input_per_1m + tokens_out / 1e6 * settings.newsroom_price_output_per_1m, 4
        )
    category = _CLASSIFICATION["primary_category"].as_string().label("category")
    categories = dict(session.execute(select(category, func.count()).where(_has_classification()).group_by(category)).all())
    by_category = [
        CountBy(key=key, label=label, count=categories.get(key, 0)) for key, label in NEWS_CATEGORY_LABELS.items()
    ]
    publishers = [
        PublisherCount(id=sid, name=name, articles=total, classified=classified)
        for sid, name, total, classified in session.execute(
            select(
                Source.id,
                Source.name,
                func.count(SourceItem.id),
                func.count(SourceItem.id).filter(_has_classification()),
            )
            .join(SourceItem, SourceItem.source_id == Source.id)
            .group_by(Source.id, Source.name)
            .order_by(func.count(SourceItem.id).desc(), Source.name)
            .limit(25)
        )
    ]
    return NewsroomSummary(
        total_articles=count(),
        collected_today=count(SourceItem.received_at >= start),
        classified_today=count(_has_classification(), classified_at >= start),
        pending_classification=count(SourceItem.processing_status.in_(PENDING_STATUSES)),
        failures=count(SourceItem.processing_status.in_(FAILED_STATUSES)),
        feeds=feed_health(session, settings),
        usage_today=UsageToday(input_tokens=tokens_in, output_tokens=tokens_out, estimated_cost_usd=cost),
        by_category=by_category,
        publishers=publishers,
        generated_at=datetime.now(UTC),
    )

