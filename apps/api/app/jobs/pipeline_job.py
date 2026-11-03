"""One article-pipeline cycle: screen -> fetch full articles -> redact -> OpenAI -> candidates.

``run_pipeline`` is the entry point shared by the scheduler (``python -m app.jobs.scheduler``)
and the one-off command (``python scripts/run_pipeline_once.py``). All logic lives in
``app.services.pipeline``; this module only wires it to settings.

Without ``OPENAI_API_KEY`` the screening and article-fetching stages still run, so
articles are ready and waiting as soon as a key is configured.
"""

from __future__ import annotations

import logging

from app.core.config import Settings, get_settings
from app.core.database import get_engine
from app.ingestion.article import ArticleFetcher
from app.services.extraction import ExtractorUnavailable, OpenAIExtractor
from app.services.pipeline import PipelineRunner, PipelineSummary

log = logging.getLogger(__name__)


def build_runner(settings: Settings | None = None) -> PipelineRunner:
    settings = settings or get_settings()
    try:
        extractor = OpenAIExtractor.from_settings(settings)
    except ExtractorUnavailable as exc:
        log.warning("Extraction disabled for this cycle: %s", exc)
        extractor = None
    fetcher = ArticleFetcher(
        timeout=settings.article_fetch_timeout_seconds,
        delay=settings.article_fetch_delay_seconds,
        max_bytes=settings.article_max_bytes,
        min_words=settings.article_min_words,
    )
    return PipelineRunner(
        get_engine(),
        fetch_article=fetcher,
        extractor=extractor,
        batch_size=settings.pipeline_batch_size,
        max_attempts=settings.pipeline_max_attempts,
        min_confidence=settings.extraction_min_confidence,
    )


def run_pipeline() -> PipelineSummary | None:
    """The scheduled job. Item-level problems are recorded; a failure of the cycle itself
    (e.g. PostgreSQL is down) is logged and re-raised."""
    settings = get_settings()
    if not settings.pipeline_enabled:
        log.warning("Article pipeline is disabled (PIPELINE_ENABLED=false)")
        return None
    try:
        return build_runner(settings).run()
    except Exception:
        log.exception("Article pipeline cycle failed")
        raise
