"""One RSS polling cycle: poll every enabled RSS source through the ingestion service.

``poll_rss_feeds`` is the single entry point shared by the scheduler
(``python -m app.jobs.scheduler``) and the one-off command
(``python scripts/run_rss_once.py``). It only orchestrates: fetching, parsing,
locking, de-duplication and run tracking live in ``app.ingestion``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.ingestion.rss import (
    SKIPPED,
    FetchFn,
    RssIngestor,
    SourceOutcome,
    SourceRef,
    safe_error_message,
)
from app.models import Source
from app.models.enums import IngestionStatus, SourceKind

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollSummary:
    """Totals for one polling cycle."""

    sources: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    seconds: float = 0.0

    @classmethod
    def from_outcomes(cls, outcomes: Sequence[SourceOutcome], seconds: float) -> PollSummary:
        def count(status: str) -> int:
            return sum(o.status == status for o in outcomes)

        return cls(
            sources=len(outcomes),
            succeeded=count(IngestionStatus.SUCCEEDED.value),
            failed=count(IngestionStatus.FAILED.value),
            skipped=count(SKIPPED),
            fetched=sum(o.fetched for o in outcomes),
            inserted=sum(o.inserted for o in outcomes),
            duplicates=sum(o.duplicates for o in outcomes),
            seconds=seconds,
        )


def load_enabled_rss_sources(engine: Engine) -> list[SourceRef]:
    """Enabled RSS sources, read in one short transaction that closes before any HTTP."""
    query = (
        select(Source.id, Source.name, Source.feed_url)
        .where(Source.kind == SourceKind.RSS.value, Source.enabled.is_(True), Source.feed_url.is_not(None))
        .order_by(Source.name)
    )
    with Session(engine) as db:
        return [SourceRef(id=row.id, name=row.name, feed_url=row.feed_url) for row in db.execute(query)]


def _poll_one(ingestor: RssIngestor, source: SourceRef) -> SourceOutcome:
    try:
        return ingestor.ingest(source)
    except Exception as exc:  # noqa: BLE001 - e.g. database hiccup; other sources must still run
        message = safe_error_message(exc)
        log.warning("%s: poll failed (will retry next cycle): %s", source.name, message)
        return SourceOutcome(source.name, IngestionStatus.FAILED.value, error=message)


def poll_sources(engine: Engine, *, fetch: FetchFn | None = None, max_workers: int = 1) -> PollSummary:
    """Poll every enabled RSS source once and return the totals."""
    started = time.monotonic()
    sources = load_enabled_rss_sources(engine)
    log.info("RSS poll cycle started: %d enabled RSS source(s)", len(sources))

    outcomes: list[SourceOutcome] = []
    if sources:
        ingestor = RssIngestor(engine, fetch=fetch)
        pool = ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(sources))), thread_name_prefix="rss-poll")
        try:
            outcomes = list(pool.map(lambda source: _poll_one(ingestor, source), sources))
        finally:  # on Ctrl+C: let in-flight sources finish cleanly, drop the ones not yet started
            pool.shutdown(wait=True, cancel_futures=True)

    summary = PollSummary.from_outcomes(outcomes, time.monotonic() - started)
    log.info(
        "RSS poll cycle finished: sources=%d succeeded=%d failed=%d skipped=%d "
        "fetched=%d new=%d duplicates=%d in %.1fs",
        summary.sources, summary.succeeded, summary.failed, summary.skipped,
        summary.fetched, summary.inserted, summary.duplicates, summary.seconds,
    )
    return summary


def poll_rss_feeds() -> None:
    """The scheduled job. Per-source problems are recorded and logged; only a failure
    of the cycle itself (e.g. PostgreSQL is down) is raised, after being logged."""
    try:
        poll_sources(get_engine(), max_workers=get_settings().rss_poll_max_workers)
    except Exception:
        log.exception("RSS poll cycle failed")
        raise
