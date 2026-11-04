"""One social polling cycle: poll every *due*, enabled, allow-listed account once.

Shared by the scheduler (``python -m app.jobs.scheduler``) and the one-off command
(``python scripts/run_social_once.py``). Accounts are polled one after another: every poll is
a paid Actor run, and the per-account interval (not the cycle length) decides how often an
account is actually read.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta

from sqlalchemy import Engine

from app.core.config import Settings, get_settings
from app.core.database import get_engine
from app.ingestion.rss import SKIPPED
from app.ingestion.social.poller import SocialIngestor, SocialOutcome
from app.ingestion.social.runner import ActorRunner, ApifyActorRunner
from app.models.enums import IngestionStatus

log = logging.getLogger(__name__)


def build_ingestor(engine: Engine, runner: ActorRunner, settings: Settings) -> SocialIngestor:
    return SocialIngestor(
        engine,
        runner,
        post_max_chars=settings.social_post_max_chars,
        run_timeout_seconds=settings.social_run_timeout_seconds,
        max_charge_usd=settings.social_max_charge_usd_per_run,
        max_runs_per_day=settings.social_max_runs_per_day,
        first_run_lookback_hours=settings.social_first_run_lookback_hours,
        retry_after_error=timedelta(minutes=settings.social_retry_after_error_minutes),
    )


def poll_social(
    engine: Engine,
    settings: Settings,
    *,
    runner: ActorRunner | None = None,
    only: uuid.UUID | None = None,
    force: bool = False,
    lookback_hours: int | None = None,
) -> list[SocialOutcome]:
    """Poll due accounts (or just ``only``, ignoring its interval when ``force``)."""
    token = settings.apify_api_token.get_secret_value() if settings.apify_api_token else ""
    if runner is None and not token:
        log.warning("Social ingestion skipped: APIFY_API_TOKEN is not set")
        return []

    ingestor = build_ingestor(engine, runner or ApifyActorRunner(token), settings)  # building the client makes no request
    ids = [only] if only is not None else [source.source_id for source in ingestor.due_sources()]
    if not ids:
        log.info("Social poll cycle: no account is due")
        return []

    started = time.monotonic()
    outcomes = [ingestor.ingest(source_id, force=force, lookback_hours=lookback_hours) for source_id in ids]
    log.info(
        "Social poll cycle finished: accounts=%d succeeded=%d partial=%d failed=%d skipped=%d new=%d in %.1fs",
        len(outcomes),
        sum(o.status == IngestionStatus.SUCCEEDED.value for o in outcomes),
        sum(o.status == IngestionStatus.PARTIAL.value for o in outcomes),
        sum(o.status == IngestionStatus.FAILED.value for o in outcomes),
        sum(o.status == SKIPPED for o in outcomes),
        sum(o.inserted for o in outcomes),
        time.monotonic() - started,
    )
    return outcomes


def poll_social_sources() -> None:
    """The scheduled job. Per-account problems are recorded; only a failure of the cycle itself is raised."""
    settings = get_settings()
    if not settings.social_ingestion_enabled:
        log.info("Social ingestion is disabled (SOCIAL_INGESTION_ENABLED=false)")
        return
    try:
        poll_social(get_engine(), settings)
    except Exception:
        log.exception("Social poll cycle failed")
        raise
