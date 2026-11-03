"""The polling job: one cycle over every enabled RSS source."""

import logging
import threading
import time

import pytest
from sqlalchemy import func, select, text

import db_factories as f
from app.ingestion.feeds import Article, SourceResult
from app.ingestion.rss import advisory_lock_key
from app.jobs import rss_poll
from app.models import IngestionRun, Source, SourceItem
from feed_server import rss_document

pytestmark = pytest.mark.usefixtures("migrated_engine")


def article(n: int, **overrides) -> Article:
    values = dict(source="Test", title=f"Headline {n}", url=f"https://news.example.test/story-{n}/",
                  guid=f"guid-{n}", summary=f"Summary {n}.", content_text=f"Body {n}.", word_count=2)
    values.update(overrides)
    return Article(**values)


class FeedsByUrl:
    """Fake ``fetch_rss`` answering per feed URL: a list of articles, an error string, or an exception."""

    def __init__(self, responses: dict, delay: float = 0.0):
        self.responses, self.delay = responses, delay
        self.active = self.peak = 0
        self._lock = threading.Lock()

    def __call__(self, name, url):
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            time.sleep(self.delay)
            response = self.responses[url]
            if isinstance(response, Exception):
                raise response
            if isinstance(response, str):
                return [], SourceResult(name, "rss", False, 0, 0.0, response)
            return list(response), SourceResult(name, "rss", True, len(response), 0.0)
        finally:
            with self._lock:
                self.active -= 1


def add_source(session, **overrides) -> Source:
    source = f.make_source(session)
    for key, value in overrides.items():
        setattr(source, key, value)
    session.commit()
    return source


def runs_by_source(session) -> dict:
    return {r.source_id: r for r in session.scalars(select(IngestionRun))}


# --- which sources are polled ---------------------------------------------------


def test_only_enabled_rss_sources_with_a_feed_url_are_loaded(migrated_engine, session):
    enabled = add_source(session)
    add_source(session, enabled=False)
    add_source(session, kind="manual", feed_url=None)

    loaded = rss_poll.load_enabled_rss_sources(migrated_engine)

    assert [s.id for s in loaded] == [enabled.id]
    assert (loaded[0].name, loaded[0].feed_url) == (enabled.name, enabled.feed_url)


def test_a_cycle_with_no_enabled_sources_is_a_quiet_no_op(migrated_engine, session, caplog):
    caplog.set_level(logging.INFO)

    summary = rss_poll.poll_sources(migrated_engine)

    assert (summary.sources, summary.succeeded, summary.failed, summary.skipped) == (0, 0, 0, 0)
    assert "0 enabled" in caplog.text


# --- one bad source never stops the cycle -----------------------------------------


def test_a_failing_feed_does_not_stop_the_other_feeds(migrated_engine, session):
    broken = add_source(session)
    crashing = add_source(session)
    healthy = add_source(session)
    fetch = FeedsByUrl({
        broken.feed_url: "503 Service Unavailable",
        crashing.feed_url: RuntimeError("parser blew up"),
        healthy.feed_url: [article(1), article(2)],
    })

    summary = rss_poll.poll_sources(migrated_engine, fetch=fetch)

    assert (summary.sources, summary.succeeded, summary.failed, summary.skipped) == (3, 1, 2, 0)
    assert (summary.fetched, summary.inserted, summary.duplicates) == (2, 2, 0)
    by_source = runs_by_source(session)
    assert by_source[broken.id].status == "failed" and "503" in by_source[broken.id].error_message
    assert by_source[crashing.id].status == "failed" and "parser blew up" in by_source[crashing.id].error_message
    assert by_source[healthy.id].status == "succeeded"
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 2


def test_a_source_that_failed_is_polled_again_on_the_next_cycle(migrated_engine, session):
    source = add_source(session)
    fetch = FeedsByUrl({source.feed_url: "timeout"})
    rss_poll.poll_sources(migrated_engine, fetch=fetch)

    fetch.responses[source.feed_url] = [article(1)]
    summary = rss_poll.poll_sources(migrated_engine, fetch=fetch)

    assert (summary.succeeded, summary.inserted) == (1, 1)
    assert sorted(r.status for r in session.scalars(select(IngestionRun))) == ["failed", "succeeded"]


def test_a_source_held_by_another_scheduler_is_skipped_and_the_rest_continue(migrated_engine, session):
    held = add_source(session)
    free = add_source(session)
    fetch = FeedsByUrl({held.feed_url: [article(1)], free.feed_url: [article(2)]})

    with migrated_engine.connect() as other_scheduler:
        other_scheduler.execute(text("SELECT pg_advisory_lock(CAST(:k AS BIGINT))"), {"k": advisory_lock_key(held.id)})
        summary = rss_poll.poll_sources(migrated_engine, fetch=fetch)
        other_scheduler.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"), {"k": advisory_lock_key(held.id)})

    assert (summary.succeeded, summary.skipped, summary.failed) == (1, 1, 0)
    assert list(runs_by_source(session)) == [free.id]  # the skipped source left no run behind


# --- parallelism -------------------------------------------------------------------


def test_sources_are_fetched_in_parallel_up_to_the_worker_limit(migrated_engine, session):
    sources = [add_source(session) for _ in range(4)]
    fetch = FeedsByUrl({s.feed_url: [article(i)] for i, s in enumerate(sources)}, delay=0.3)

    summary = rss_poll.poll_sources(migrated_engine, fetch=fetch, max_workers=2)

    assert summary.succeeded == 4
    assert fetch.peak == 2  # concurrent, but never more than asked for


def test_one_worker_means_strictly_one_source_at_a_time(migrated_engine, session):
    sources = [add_source(session) for _ in range(3)]
    fetch = FeedsByUrl({s.feed_url: [article(i)] for i, s in enumerate(sources)}, delay=0.1)

    rss_poll.poll_sources(migrated_engine, fetch=fetch, max_workers=1)

    assert fetch.peak == 1


# --- logging -------------------------------------------------------------------------


def test_the_cycle_logs_sources_new_duplicates_and_errors(migrated_engine, session, caplog):
    good = add_source(session)
    bad = add_source(session)
    fetch = FeedsByUrl({good.feed_url: [article(1), article(2)], bad.feed_url: "boom"})
    rss_poll.poll_sources(migrated_engine, fetch=fetch)  # warm-up: stores 2 items
    caplog.clear()
    caplog.set_level(logging.INFO)

    rss_poll.poll_sources(migrated_engine, fetch=fetch)

    assert f"{good.name}: fetched=2 new=0 duplicates=2" in caplog.text
    assert f"{bad.name}: poll failed" in caplog.text
    assert "sources=2 succeeded=1 failed=1 skipped=0 fetched=2 new=0 duplicates=2" in caplog.text


# --- the real thing: real parser, real HTTP, real database --------------------------------


def test_poll_rss_feeds_runs_the_existing_parser_and_dedupes_across_cycles(
    migrated_engine, session, feed_server, monkeypatch, caplog
):
    url = feed_server.serve("/herald", rss_document([
        {"title": f"Story {n}", "guid": f"g-{n}", "link": f"https://news.example.test/story-{n}/?utm_source=rss"}
        for n in range(1, 16)
    ]))
    source = add_source(session, feed_url=url)
    monkeypatch.setattr(rss_poll, "get_engine", lambda: migrated_engine)
    caplog.set_level(logging.INFO)

    rss_poll.poll_rss_feeds()  # poll 1
    rss_poll.poll_rss_feeds()  # poll 2: same 15 entries

    first, second = session.scalars(select(IngestionRun).order_by(IngestionRun.started_at)).all()
    assert (first.fetched_count, first.inserted_count, first.duplicate_count) == (15, 15, 0)
    assert (second.fetched_count, second.inserted_count, second.duplicate_count) == (15, 0, 15)
    assert session.scalar(select(func.count()).select_from(SourceItem).where(SourceItem.source_id == source.id)) == 15
    assert feed_server.hits["/herald"] == 2
    assert f"{source.name}: fetched=15 new=15 duplicates=0" in caplog.text
    assert f"{source.name}: fetched=15 new=0 duplicates=15" in caplog.text
    assert url not in caplog.text  # logs name sources, they don't echo feed URLs


def test_a_cycle_level_failure_is_logged_and_raised_for_the_caller(monkeypatch, caplog):
    def database_down(engine):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(rss_poll, "get_engine", lambda: object())
    monkeypatch.setattr(rss_poll, "load_enabled_rss_sources", database_down)

    with pytest.raises(RuntimeError, match="connection refused"):
        rss_poll.poll_rss_feeds()

    assert "RSS poll cycle failed" in caplog.text
