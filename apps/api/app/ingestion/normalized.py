"""The source-agnostic report that every ingestion adapter produces.

RSS (``app.ingestion.rss``) wrote ``source_items`` rows directly, so until social media arrived
there was no explicit contract. ``NormalizedReport`` is that contract: an adapter (RSS, Facebook,
later X / TikTok) turns whatever it collected into reports, and ``report_row`` turns a report into
a ``source_items`` row. Everything after that row (screening, redaction, OpenAI extraction,
deduplication, editorial review) lives in ``app.services.pipeline`` and knows nothing about where
a report came from beyond ``source_metadata["content_kind"]``.

RSS keeps its own row builder; moving it onto this contract is a separate, optional clean-up.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.ingestion.rss import canonicalize_url

ARTICLE = "article"  # a news item whose full text is fetched from its URL
SOCIAL_POST = "social_post"  # the post text *is* the content; no page to fetch

TITLE_MAX_CHARS = 140


@dataclass(frozen=True)
class NormalizedReport:
    external_id: str  # the platform's / feed's own id; unique per source
    url: str  # canonical location of the report
    text: str  # the content (post text, or an article's summary)
    published_at: datetime | None = None
    title: str | None = None  # derived from the text when absent
    content_kind: str = SOCIAL_POST
    language: str | None = None
    image_url: str | None = None
    linked_article_url: str | None = None  # an external article the post points to
    extra: dict[str, Any] = field(default_factory=dict)  # small, non-sensitive provenance


def make_title(text: str) -> str:
    """First non-empty line of a post, collapsed and shortened."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = " ".join(first.split())
    if len(first) > TITLE_MAX_CHARS:
        first = first[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return first or "Untitled"


def _scrub(value: str) -> str:
    return value.replace("\x00", "")  # PostgreSQL text cannot hold NUL


def report_row(report: NormalizedReport, source_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    """A ``source_items`` insert row. Text is stored unredacted-but-flagged exactly like RSS:
    the pipeline's screening stage redacts title and excerpt before anything else reads them."""
    canonical = canonicalize_url(report.url)
    text = _scrub(report.text).strip()
    metadata = {
        "url": canonical,
        "content_kind": report.content_kind,
        "language": report.language,
        "image_url": report.image_url,
        "redaction": "not_applied",
        **report.extra,
    }
    if report.linked_article_url:
        metadata["linked_article_url"] = report.linked_article_url
    return {
        "source_id": source_id,
        "ingestion_run_id": run_id,
        "external_id": report.external_id,
        "canonical_url": canonical,
        "title_redacted": _scrub(report.title or make_title(text)),
        "excerpt_redacted": text or None,
        "published_at": report.published_at,
        "source_metadata": metadata,
    }
