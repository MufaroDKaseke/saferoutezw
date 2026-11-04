"""Persist RSS entries as ``source_items``, one tracked ``ingestion_run`` per poll.

This is the only place that joins the existing feed parser (``feeds.fetch_rss``)
to the database. The scheduler and the one-off script both reach it through
``app.jobs.rss_poll``; neither contains parsing or persistence logic.

Design points
-------------
* **No transaction is open while a feed downloads.** The HTTP request runs with
  no database transaction at all; each database step uses its own short
  transaction (start run -> save items -> finish run).
* **Cross-process safety.** A PostgreSQL session-level advisory lock, taken with
  the non-blocking ``pg_try_advisory_lock``, stops two scheduler processes that
  share a database from polling the same source at once. It lives on a dedicated
  AUTOCOMMIT connection, so it spans the slow HTTP call without a transaction.
* **De-duplication is the database's job.** Items are inserted with
  ``ON CONFLICT DO NOTHING`` against the existing ``(source_id, external_id)``
  and ``(source_id, canonical_url)`` unique constraints, so concurrent or
  repeated polls cannot create duplicates whatever Python believed beforehand.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import Engine, func, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.feeds import Article, SourceResult, _strip_tracking, fetch_rss
from app.models import IngestionRun, SourceItem
from app.models.enums import IngestionStatus

log = logging.getLogger(__name__)

FetchFn = Callable[[str, str], "tuple[list[Article], SourceResult]"]

#: Outcome status for a source another worker was already polling. It is logged
#: but not stored: ``ingestion_runs.status`` has no such value (and adding one
#: would need a migration for no benefit).
SKIPPED = "skipped"

ERROR_MESSAGE_MAX = 500
EXCERPT_FALLBACK_CHARS = 500


@dataclass(frozen=True)
class SourceRef:
    """What the poller needs to know about a source (detached from any session)."""

    id: uuid.UUID
    name: str
    feed_url: str


@dataclass(frozen=True)
class SourceOutcome:
    """Result of polling one source: ``succeeded``, ``failed`` or ``skipped``."""

    source_name: str
    status: str
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    error: str | None = None
    run_id: uuid.UUID | None = None


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def canonicalize_url(url: str) -> str:
    """Stable per-article URL: no tracking params or fragment, lower-case scheme and
    host, no trailing slash. The path keeps its case (paths are case-sensitive)."""
    parts = urlsplit(_strip_tracking(url.strip()))
    path = parts.path.rstrip("/") or ("/" if parts.netloc else "")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def advisory_lock_key(source_id: uuid.UUID) -> int:
    """Deterministic signed 64-bit key, identical in every scheduler process."""
    digest = hashlib.blake2b(f"saferoutezw:rss_source:{source_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


@contextmanager
def source_advisory_lock(engine: Engine, key: int, label: str) -> Iterator[bool]:
    """Try to take a session-level advisory lock without waiting; always release it.

    The lock is tied to the connection, not to a transaction, so the connection
    runs in AUTOCOMMIT mode: it holds the lock but never an open transaction.
    Shared by RSS and social polling (each passes its own key).
    """
    params = {"k": key}
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    acquired = False
    try:
        acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(CAST(:k AS BIGINT))"), params).scalar())
        yield acquired
    finally:
        try:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"), params)
        except Exception:  # noqa: BLE001
            # Never return a connection that may still hold the lock to the pool;
            # closing it for real makes PostgreSQL release the lock.
            log.warning("Could not release the lock for %s cleanly; dropping its connection", label)
            conn.invalidate()
        finally:
            conn.close()


_USERINFO = re.compile(r"(?<=://)[^/@\s]+@")
_SECRET_PARAM = re.compile(
    r"(?i)\b(token|access_token|key|api_key|apikey|secret|password|passwd|auth|signature)=[^&\s'\"]+"
)


def safe_error_message(error: BaseException | str) -> str:
    """Error text that is safe to store and log: no URL credentials or secret query values."""
    message = error if isinstance(error, str) else f"{type(error).__name__}: {error}"
    message = _USERINFO.sub("***@", message)
    message = _SECRET_PARAM.sub(lambda m: f"{m.group(1)}=***", message)
    return message[:ERROR_MESSAGE_MAX]


def _scrub(value: Any) -> Any:
    """Remove NUL characters, which PostgreSQL text/JSONB cannot store."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _article_row(article: Article, source_id: uuid.UUID, run_id: uuid.UUID) -> dict[str, Any]:
    canonical = canonicalize_url(article.url)
    excerpt = (article.summary or article.content_text[:EXCERPT_FALLBACK_CHARS]).strip()
    return _scrub({
        "source_id": source_id,
        "ingestion_run_id": run_id,
        "external_id": article.guid.strip() or None,
        "canonical_url": canonical,
        "title_redacted": article.title.strip() or "Untitled",
        "excerpt_redacted": excerpt or None,
        "published_at": _parse_time(article.published),
        "source_metadata": {
            "url": canonical,
            "authors": article.authors,
            "categories": article.categories,
            "image_url": article.image_url,
            "language": article.language,
            "word_count": article.word_count,
            "content_source": article.content_source,
            # The text columns are named *_redacted, but redaction is a later pipeline
            # stage that does not exist yet: this is the headline/excerpt as published.
            "redaction": "not_applied",
        },
    })


def _unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop repeats inside one feed. A courtesy only: the database is the authority."""
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    unique = []
    for row in rows:
        if row["canonical_url"] in seen_urls or (row["external_id"] and row["external_id"] in seen_ids):
            continue
        seen_urls.add(row["canonical_url"])
        if row["external_id"]:
            seen_ids.add(row["external_id"])
        unique.append(row)
    return unique


def _insert_items(db: Session, rows: list[dict[str, Any]]) -> int:
    """Insert rows, silently skipping any that violate a unique key; returns rows stored."""
    if not rows:
        return 0
    statement = insert(SourceItem).values(rows).on_conflict_do_nothing().returning(SourceItem.id)
    return len(db.execute(statement).all())


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class RssIngestor:
    """Polls one source at a time: lock, record run, fetch, save, finish run."""

    def __init__(self, engine: Engine, fetch: FetchFn | None = None) -> None:
        self._engine = engine
        self._fetch = fetch or fetch_rss
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def ingest(self, source: SourceRef) -> SourceOutcome:
        with self._source_lock(source) as acquired:
            if not acquired:
                log.info("Skipped %s: another worker is already polling it", source.name)
                return SourceOutcome(source.name, SKIPPED)

            run_id = self._start_run(source)
            try:
                articles, result = self._fetch(source.name, source.feed_url)
                if not result.ok:
                    return self._fail(source, run_id, result.error or "feed could not be fetched")
                inserted = self._save(source, run_id, articles)
            except Exception as exc:  # noqa: BLE001 - one bad feed must not stop the others
                return self._fail(source, run_id, exc)
            except BaseException:  # Ctrl+C / SystemExit: do not leave the run "running"
                self._fail(source, run_id, "interrupted before completion")
                raise

            fetched = len(articles)
            duplicates = fetched - inserted
            self._finish(run_id, IngestionStatus.SUCCEEDED, fetched, inserted, duplicates, 0, None)
            log.info("%s: fetched=%d new=%d duplicates=%d", source.name, fetched, inserted, duplicates)
            return SourceOutcome(
                source.name, IngestionStatus.SUCCEEDED.value, fetched, inserted, duplicates, None, run_id
            )

    # -- locking -----------------------------------------------------------------
    def _source_lock(self, source: SourceRef):
        return source_advisory_lock(self._engine, advisory_lock_key(source.id), source.name)

    # -- short, separate transactions ----------------------------------------------
    def _start_run(self, source: SourceRef) -> uuid.UUID:
        with self._sessions.begin() as db:
            run = IngestionRun(source_id=source.id, status=IngestionStatus.RUNNING.value)
            db.add(run)
            db.flush()
            return run.id

    def _save(self, source: SourceRef, run_id: uuid.UUID, articles: list[Article]) -> int:
        rows = _unique_rows([_article_row(a, source.id, run_id) for a in articles])
        with self._sessions.begin() as db:
            return _insert_items(db, rows)

    def _finish(
        self, run_id: uuid.UUID, status: IngestionStatus, fetched: int, inserted: int,
        duplicates: int, errors: int, message: str | None,
    ) -> None:
        with self._sessions.begin() as db:
            db.execute(
                update(IngestionRun)
                .where(IngestionRun.id == run_id)
                .values(
                    status=status.value, completed_at=func.now(), fetched_count=fetched,
                    inserted_count=inserted, duplicate_count=duplicates, error_count=errors,
                    error_message=message,
                )
            )

    def _fail(self, source: SourceRef, run_id: uuid.UUID, error: BaseException | str) -> SourceOutcome:
        message = safe_error_message(error)
        self._finish(run_id, IngestionStatus.FAILED, 0, 0, 0, 1, message)
        log.warning("%s: poll failed (will retry next cycle): %s", source.name, message)
        return SourceOutcome(
            source.name, IngestionStatus.FAILED.value, error=message, run_id=run_id
        )
