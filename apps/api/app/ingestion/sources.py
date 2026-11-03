"""Register the configured news feeds as rows in the ``sources`` table."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.feeds import RSS_FEEDS
from app.models import Source
from app.models.enums import SourceKind


def seed_rss_sources(db: Session) -> int:
    """Insert any feed from ``RSS_FEEDS`` that is not in ``sources`` yet; returns how many.

    Existing rows are never touched, so a developer who disabled a feed or changed
    its interval keeps that choice. Everything else comes from the column defaults:
    enabled, and ``verification_tier`` = ``unverified`` (editors raise it deliberately).
    The caller commits.
    """
    rows = [{"name": name, "kind": SourceKind.RSS.value, "feed_url": url} for name, url in RSS_FEEDS.items()]
    statement = insert(Source).values(rows).on_conflict_do_nothing().returning(Source.id)
    return len(db.execute(statement).all())
