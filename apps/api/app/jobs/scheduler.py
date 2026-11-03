"""Local stand-in for a production cron job: poll RSS feeds on a fixed interval.

Run it in its own terminal, separately from the FastAPI server::

    cd apps/api
    python -m app.jobs.scheduler

It only *triggers* ``app.jobs.rss_poll.poll_rss_feeds``; all fetching, parsing,
locking and persistence live in ``app.ingestion``. Nothing here is imported by
the FastAPI application, so the API never starts a scheduler.

Settings (root ``.env``): ``RSS_POLL_INTERVAL_SECONDS`` (default 180),
``RSS_POLL_ON_STARTUP`` (default true), ``RSS_SCHEDULER_ENABLED`` (default true).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.util import undefined

from app.core.config import Settings, get_settings
from app.jobs.logging_config import configure_logging
from app.jobs.pipeline_job import run_pipeline
from app.jobs.rss_poll import poll_rss_feeds

log = logging.getLogger(__name__)

JOB_ID = "rss_polling"
PIPELINE_JOB_ID = "article_pipeline"
TIMEZONE = "Africa/Harare"


def register_polling_job(
    scheduler: BlockingScheduler,
    *,
    interval_seconds: int,
    poll_on_startup: bool,
    job: Callable[[], None] = poll_rss_feeds,
) -> None:
    """Add (or replace) the single RSS polling job.

    ``IntervalTrigger`` is fixed-rate: runs are scheduled ``interval_seconds`` apart
    regardless of how long the previous run took. ``max_instances=1`` stops a slow
    cycle overlapping the next one in this process (cross-process safety is the
    database advisory lock's job); ``coalesce`` folds several missed ticks, e.g.
    after the laptop slept, into one run.
    """
    scheduler.add_job(
        job,
        trigger=IntervalTrigger(seconds=interval_seconds, timezone=TIMEZONE),
        id=JOB_ID,
        name="RSS polling",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=interval_seconds,
        next_run_time=datetime.now(ZoneInfo(TIMEZONE)) if poll_on_startup else undefined,
    )


def register_pipeline_job(
    scheduler: BlockingScheduler,
    *,
    interval_seconds: int,
    job: Callable[[], object] = run_pipeline,
) -> None:
    """Add (or replace) the article pipeline job (screen -> fetch -> redact -> OpenAI).

    It runs beside RSS polling on its own interval. The first run waits one interval so
    the first polling cycle has time to store items. ``max_instances=1`` stops a slow
    cycle (OpenAI calls) overlapping the next; the pipeline also holds a database
    advisory lock, so two scheduler processes cannot run it at once.
    """
    scheduler.add_job(
        job,
        trigger=IntervalTrigger(seconds=interval_seconds, timezone=TIMEZONE),
        id=PIPELINE_JOB_ID,
        name="Article pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=interval_seconds,
    )


def build_scheduler(
    *,
    interval_seconds: int,
    poll_on_startup: bool,
    job: Callable[[], None] = poll_rss_feeds,
    pipeline_interval_seconds: int | None = None,
    pipeline_job: Callable[[], object] = run_pipeline,
) -> BlockingScheduler:
    """RSS polling job, plus the article pipeline job when ``pipeline_interval_seconds`` is set."""
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    register_polling_job(scheduler, interval_seconds=interval_seconds, poll_on_startup=poll_on_startup, job=job)
    if pipeline_interval_seconds is not None:
        register_pipeline_job(scheduler, interval_seconds=pipeline_interval_seconds, job=pipeline_job)
    return scheduler


def run_scheduler(scheduler: BlockingScheduler) -> int:
    """Block until stopped. Ctrl+C lets a cycle that is already running finish."""
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Stopping RSS scheduler: letting any poll already running finish first")
        scheduler.shutdown(wait=True)
        log.info("RSS scheduler stopped")
    return 0


def main(settings: Settings | None = None) -> int:
    configure_logging()
    settings = settings or get_settings()
    if not settings.rss_scheduler_enabled:
        log.warning("RSS scheduler is disabled (RSS_SCHEDULER_ENABLED=false); nothing to do")
        return 0

    scheduler = build_scheduler(
        interval_seconds=settings.rss_poll_interval_seconds,
        poll_on_startup=settings.rss_poll_on_startup,
        pipeline_interval_seconds=settings.pipeline_interval_seconds if settings.pipeline_enabled else None,
    )
    log.info(
        "RSS scheduler started: every %d s (%s), first poll %s. Press Ctrl+C to stop.",
        settings.rss_poll_interval_seconds, TIMEZONE,
        "now" if settings.rss_poll_on_startup else f"in {settings.rss_poll_interval_seconds} s",
    )
    if settings.pipeline_enabled:
        log.info("Article pipeline job: every %d s (screen, fetch, redact, extract)", settings.pipeline_interval_seconds)
    return run_scheduler(scheduler)


if __name__ == "__main__":
    raise SystemExit(main())
