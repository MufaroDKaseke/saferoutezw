"""Backfill older articles from the RSS sources by paging their feeds (``?paged=N``).

Feeds normally hold only their newest items. WordPress feeds (which almost all our
sources are) also serve older pages through ``?paged=N`` on the same URL, so this walks
those pages until it passes the cut-off date, runs out of items, or hits an error.

It is polite and never works around a block: one request at a time per source, a pause
between pages, and a source that answers with an error (403, 429, 415...) is left as it
is - the backfill stops for that source and says so. Articles older than the cut-off are
dropped. New rows are stored through the normal ingestion service (de-duplicated), so
the article pipeline picks them up as usual.

    python scripts/backfill_rss.py --days 60 [--max-pages 40] [--delay 1.5] [--source NAME]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import get_engine  # noqa: E402
from app.ingestion.feeds import Article, SourceResult, fetch_rss  # noqa: E402
from app.ingestion.rss import RssIngestor  # noqa: E402
from app.jobs.logging_config import configure_logging  # noqa: E402
from app.jobs.rss_poll import load_enabled_rss_sources  # noqa: E402

log = logging.getLogger("backfill_rss")


def page_url(feed_url: str, page: int) -> str:
    separator = "&" if "?" in feed_url else "?"
    return feed_url if page == 1 else f"{feed_url}{separator}paged={page}"


def _published(article: Article) -> datetime | None:
    try:
        return datetime.fromisoformat(article.published) if article.published else None
    except ValueError:
        return None


def make_fetch(cutoff: datetime, max_pages: int, delay: float):
    """A ``FetchFn`` that returns every article newer than ``cutoff`` across feed pages."""

    def fetch(name: str, url: str) -> tuple[list[Article], SourceResult]:
        start = time.time()
        collected: list[Article] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            articles, result = fetch_rss(name, page_url(url, page))
            if not result.ok:
                if page == 1:
                    return [], result  # not reachable at all: report it, do nothing else
                log.info("%s: stopped at page %d (%s)", name, page, result.error)
                break
            fresh = [a for a in articles if a.url not in seen]
            if not fresh:
                break  # the site repeats its last page: no older items
            seen.update(a.url for a in fresh)
            dated = [(a, _published(a)) for a in fresh]
            collected.extend(a for a, when in dated if when is None or when >= cutoff)
            if dated and all(when is not None and when < cutoff for _, when in dated):
                break  # the whole page is older than the window
            time.sleep(delay)
        ok = SourceResult(name, "rss", True, len(collected), time.time() - start)
        return collected, ok

    return fetch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--max-pages", type=int, default=40)
    parser.add_argument("--delay", type=float, default=1.5, help="seconds between pages of one source")
    parser.add_argument("--source", help="only this source name")
    args = parser.parse_args(argv)

    configure_logging()
    cutoff = datetime.now(UTC) - timedelta(days=args.days)
    engine = get_engine()
    sources = [s for s in load_enabled_rss_sources(engine) if not args.source or s.name == args.source]
    ingestor = RssIngestor(engine, fetch=make_fetch(cutoff, args.max_pages, args.delay))
    log.info("Backfilling %d source(s) back to %s", len(sources), cutoff.date())
    new = failed = 0
    for source in sources:
        outcome = ingestor.ingest(source)
        new += outcome.inserted
        failed += outcome.status == "failed"
        log.info("%s: %s fetched=%d new=%d", source.name, outcome.status, outcome.fetched, outcome.inserted)
    log.info("Backfill done: %d new article(s), %d source(s) failed", new, failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
