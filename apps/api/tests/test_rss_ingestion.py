"""RSS ingestion service: persistence, de-duplication, run tracking and locking.

Runs against the disposable test database. The network is replaced by a fake
``fetch`` that returns real ``Article`` objects from the existing parser.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text

import db_factories as f
from app.ingestion import rss
from app.ingestion.feeds import Article, SourceResult
from app.ingestion.rss import RssIngestor, SourceRef, advisory_lock_key, canonicalize_url
from app.models import IngestionRun, SourceItem

pytestmark = pytest.mark.usefixtures("migrated_engine")

ADVISORY_LOCKS = (
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
    "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
)
IDLE_IN_TRANSACTION = (
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
    "AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()"
)


def article(n: int = 1, **overrides) -> Article:
    values = dict(
        source="Test", title=f"Headline {n}", url=f"https://news.example.test/story-{n}/",
        guid=f"guid-{n}", published="2026-11-03T07:00:00+00:00", summary=f"Summary {n}.",
        content_text=f"Body {n}.", word_count=2, authors=["Reporter"], categories=["News"],
        content_source="feed",
    )
    values.update(overrides)
    return Article(**values)


class FakeFeed:
    """Stands in for ``fetch_rss(name, url)``; records how it was called."""

    def __init__(self, *articles: Article, ok: bool = True, error: str = ""):
        self.articles, self.ok, self.error, self.calls = list(articles), ok, error, []

    def __call__(self, name: str, url: str):
        self.calls.append((name, url))
        if not self.ok:
            return [], SourceResult(name, "rss", False, 0, 0.0, self.error)
        return list(self.articles), SourceResult(name, "rss", True, len(self.articles), 0.0)


@pytest.fixture
def source(session) -> SourceRef:
    row = f.make_source(session)
    ref = SourceRef(id=row.id, name=row.name, feed_url=row.feed_url)
    session.commit()  # the service uses its own connections, so it must see the row
    return ref


def ingest(engine, source, *articles, **feed_options):
    feed = FakeFeed(*articles, **feed_options)
    return RssIngestor(engine, fetch=feed).ingest(source), feed


def item_count(session) -> int:
    return session.scalar(select(func.count()).select_from(SourceItem))


def runs(session) -> list[IngestionRun]:
    return list(session.scalars(select(IngestionRun).order_by(IngestionRun.started_at)))


# --- pure helpers ---------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [
    ("https://Example.TEST/a/b/?utm_source=x&id=7#frag", "https://example.test/a/b?id=7"),
    ("http://example.test/a/", "http://example.test/a"),
    ("https://example.test/", "https://example.test/"),
    ("https://example.test/Mixed/Case", "https://example.test/Mixed/Case"),
    ("https://example.test/a?utm_medium=rss&utm_campaign=z", "https://example.test/a"),
])
def test_canonical_url_is_stable_across_tracking_fragments_and_trailing_slashes(raw, expected):
    assert canonicalize_url(raw) == expected


def test_lock_key_is_stable_per_source_and_fits_a_postgres_bigint():
    import uuid

    a, b = uuid.uuid4(), uuid.uuid4()
    assert advisory_lock_key(a) == advisory_lock_key(a)
    assert advisory_lock_key(a) != advisory_lock_key(b)
    assert -(2**63) <= advisory_lock_key(a) < 2**63


# --- persistence and de-duplication ---------------------------------------------


def test_first_poll_stores_every_entry_and_records_a_succeeded_run(migrated_engine, source, session):
    outcome, _ = ingest(migrated_engine, source, article(1), article(2), article(3))

    assert (outcome.status, outcome.fetched, outcome.inserted, outcome.duplicates) == ("succeeded", 3, 3, 0)
    run = runs(session)[0]
    assert run.source_id == source.id and run.id == outcome.run_id
    assert (run.status, run.fetched_count, run.inserted_count, run.duplicate_count, run.error_count) == (
        "succeeded", 3, 3, 0, 0)
    assert run.error_message is None
    assert run.completed_at is not None and run.completed_at >= run.started_at
    items = list(session.scalars(select(SourceItem)))
    assert len(items) == 3
    assert {i.ingestion_run_id for i in items} == {run.id}
    assert {i.source_id for i in items} == {source.id}
    assert {i.processing_status for i in items} == {"pending"}  # queued for the pipeline


def test_polling_the_same_feed_again_creates_no_duplicates(migrated_engine, source, session):
    feed = FakeFeed(article(1), article(2), article(3))
    ingestor = RssIngestor(migrated_engine, fetch=feed)

    first, second = ingestor.ingest(source), ingestor.ingest(source)

    assert (first.fetched, first.inserted, first.duplicates) == (3, 3, 0)
    assert (second.fetched, second.inserted, second.duplicates) == (3, 0, 3)
    assert item_count(session) == 3
    assert [r.status for r in runs(session)] == ["succeeded", "succeeded"]
    assert [r.duplicate_count for r in runs(session)] == [0, 3]


def test_only_the_new_entry_is_inserted_when_a_feed_grows(migrated_engine, source, session):
    feed = FakeFeed(article(1), article(2))
    ingestor = RssIngestor(migrated_engine, fetch=feed)
    ingestor.ingest(source)

    feed.articles.append(article(3))
    outcome = ingestor.ingest(source)

    assert (outcome.inserted, outcome.duplicates) == (1, 2)
    assert item_count(session) == 3


def test_same_url_under_a_new_guid_is_a_duplicate(migrated_engine, source, session):
    ingest(migrated_engine, source, article(1, guid="old-guid"))

    outcome, _ = ingest(migrated_engine, source, article(1, guid="republished-guid"))

    assert (outcome.inserted, outcome.duplicates) == (0, 1)
    assert item_count(session) == 1


def test_same_guid_under_a_changed_url_is_a_duplicate(migrated_engine, source, session):
    ingest(migrated_engine, source, article(1, url="https://news.example.test/original/"))

    outcome, _ = ingest(migrated_engine, source, article(1, url="https://news.example.test/moved/"))

    assert (outcome.inserted, outcome.duplicates) == (0, 1)
    assert item_count(session) == 1


def test_tracking_parameters_do_not_defeat_de_duplication(migrated_engine, source, session):
    ingest(migrated_engine, source, article(1, guid="", url="https://news.example.test/s/"))

    outcome, _ = ingest(
        migrated_engine, source,
        article(1, guid="", url="https://News.Example.test/s?utm_source=rss#comments"))

    assert (outcome.inserted, outcome.duplicates) == (0, 1)


def test_an_entry_repeated_inside_one_feed_is_stored_once(migrated_engine, source, session):
    outcome, _ = ingest(migrated_engine, source, article(1), article(1), article(2))

    assert (outcome.fetched, outcome.inserted, outcome.duplicates) == (3, 2, 1)
    assert item_count(session) == 2


def test_the_same_entry_in_two_different_sources_is_two_items(migrated_engine, source, session):
    other_row = f.make_source(session)
    other = SourceRef(id=other_row.id, name=other_row.name, feed_url=other_row.feed_url)
    session.commit()

    ingest(migrated_engine, source, article(1))
    outcome, _ = ingest(migrated_engine, other, article(1))

    assert outcome.inserted == 1
    assert item_count(session) == 2


def test_stored_item_carries_normalised_fields_and_marks_redaction_as_pending(migrated_engine, source, session):
    ingest(migrated_engine, source, article(
        1, url="https://news.example.test/Story/?utm_source=rss", authors=["A", "B"],
        image_url="https://img.example.test/1.jpg"))

    item = session.scalars(select(SourceItem)).one()
    assert item.external_id == "guid-1"
    assert item.canonical_url == "https://news.example.test/Story"
    assert item.title_redacted == "Headline 1"
    assert item.excerpt_redacted == "Summary 1."
    assert item.published_at == datetime(2026, 11, 3, 7, 0, tzinfo=UTC)  # same instant, whatever zone PG shows
    assert item.source_metadata["authors"] == ["A", "B"]
    assert item.source_metadata["url"] == "https://news.example.test/Story"
    assert item.source_metadata["image_url"] == "https://img.example.test/1.jpg"
    # Redaction is a later pipeline stage. Until it exists, the text is stored as published.
    assert item.source_metadata["redaction"] == "not_applied"


def test_entry_without_guid_or_date_is_stored_with_only_a_url_key(migrated_engine, source, session):
    ingest(migrated_engine, source, article(1, guid="", published=None, summary="", content_text="Long body text."))

    item = session.scalars(select(SourceItem)).one()
    assert item.external_id is None
    assert item.canonical_url == "https://news.example.test/story-1"
    assert item.published_at is None
    assert item.excerpt_redacted == "Long body text."  # falls back to the start of the body


def test_nul_characters_do_not_poison_the_feed(migrated_engine, source, session):
    outcome, _ = ingest(migrated_engine, source, article(1, title="Crash\x00 on A1", authors=["Re\x00porter"]))

    assert outcome.status == "succeeded"
    item = session.scalars(select(SourceItem)).one()
    assert item.title_redacted == "Crash on A1"
    assert item.source_metadata["authors"] == ["Reporter"]


# --- failures --------------------------------------------------------------------


def test_a_feed_that_cannot_be_fetched_is_recorded_as_a_failed_run(migrated_engine, source, session):
    outcome, _ = ingest(migrated_engine, source, ok=False, error="404 Client Error: Not Found")

    assert outcome.status == "failed" and "404" in outcome.error
    run = runs(session)[0]
    assert (run.status, run.error_count, run.fetched_count, run.inserted_count) == ("failed", 1, 0, 0)
    assert "404" in run.error_message
    assert run.completed_at is not None
    assert item_count(session) == 0


def test_an_unexpected_exception_is_contained_and_recorded(migrated_engine, source, session):
    def explode(name, url):
        raise RuntimeError("socket on fire")

    outcome = RssIngestor(migrated_engine, fetch=explode).ingest(source)

    assert outcome.status == "failed"
    run = runs(session)[0]
    assert run.status == "failed" and "socket on fire" in run.error_message
    assert run.completed_at is not None


def test_ctrl_c_mid_poll_closes_the_run_and_the_lock_then_propagates(migrated_engine, source, session):
    def interrupted(name, url):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        RssIngestor(migrated_engine, fetch=interrupted).ingest(source)

    run = runs(session)[0]  # not left "running" forever
    assert run.status == "failed" and "interrupted" in run.error_message.lower()
    assert run.completed_at is not None
    with migrated_engine.connect() as probe:
        assert probe.execute(text(ADVISORY_LOCKS)).scalar() == 0


def test_a_database_error_while_saving_fails_the_run_and_stores_nothing(migrated_engine, source, session, monkeypatch):
    def broken_insert(db, rows):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(rss, "_insert_items", broken_insert)

    outcome, _ = ingest(migrated_engine, source, article(1))

    assert outcome.status == "failed"
    run = runs(session)[0]
    assert run.status == "failed" and "db exploded" in run.error_message
    assert item_count(session) == 0


def test_a_failed_poll_is_retried_normally_on_the_next_cycle(migrated_engine, source, session):
    ingest(migrated_engine, source, ok=False, error="timeout")

    outcome, _ = ingest(migrated_engine, source, article(1))

    assert outcome.status == "succeeded" and outcome.inserted == 1
    assert [r.status for r in runs(session)] == ["failed", "succeeded"]


def test_credentials_and_tokens_in_error_text_are_not_stored(migrated_engine, source, session):
    error = "401 for url: https://user:hunter2@feeds.example.test/rss?token=abc123&page=2"

    outcome, _ = ingest(migrated_engine, source, ok=False, error=error)

    run = runs(session)[0]
    for text_ in (run.error_message, outcome.error):
        assert "hunter2" not in text_ and "abc123" not in text_
        assert "feeds.example.test" in text_  # still useful for debugging


def test_long_error_text_is_truncated(migrated_engine, source, session):
    ingest(migrated_engine, source, ok=False, error="x" * 5000)

    assert len(runs(session)[0].error_message) <= 500


# --- locking and transactions ------------------------------------------------------


def test_a_source_locked_by_another_worker_is_skipped_without_fetching(migrated_engine, source, session):
    feed = FakeFeed(article(1))
    key = {"k": advisory_lock_key(source.id)}
    with migrated_engine.connect() as other_worker:  # a second scheduler process
        other_worker.execute(text("SELECT pg_advisory_lock(CAST(:k AS BIGINT))"), key)
        outcome = RssIngestor(migrated_engine, fetch=feed).ingest(source)
        other_worker.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"), key)

    assert outcome.status == "skipped"
    assert feed.calls == []
    assert runs(session) == [] and item_count(session) == 0

    # Once the other worker is done, polling resumes.
    assert RssIngestor(migrated_engine, fetch=feed).ingest(source).status == "succeeded"


def test_the_lock_does_not_block_other_sources(migrated_engine, source, session):
    other_row = f.make_source(session)
    other = SourceRef(id=other_row.id, name=other_row.name, feed_url=other_row.feed_url)
    session.commit()
    with migrated_engine.connect() as other_worker:
        other_worker.execute(text("SELECT pg_advisory_lock(CAST(:k AS BIGINT))"),
                             {"k": advisory_lock_key(source.id)})
        outcome, _ = ingest(migrated_engine, other, article(1))
        other_worker.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"),
                             {"k": advisory_lock_key(source.id)})

    assert outcome.status == "succeeded"


@pytest.mark.parametrize("scenario", ["success", "failed_feed", "exception"])
def test_the_lock_is_always_released(migrated_engine, source, session, scenario):
    def explode(name, url):
        raise RuntimeError("boom")

    if scenario == "exception":
        RssIngestor(migrated_engine, fetch=explode).ingest(source)
    else:
        ingest(migrated_engine, source, article(1), ok=scenario == "success", error="down")

    with migrated_engine.connect() as probe:
        assert probe.execute(text(ADVISORY_LOCKS)).scalar() == 0


def test_the_lock_is_held_but_no_transaction_is_open_while_the_feed_downloads(migrated_engine, source, session):
    observed = {}

    def slow_download(name, url):
        with migrated_engine.connect() as probe:  # a separate connection looking in from outside
            observed["locks"] = probe.execute(text(ADVISORY_LOCKS)).scalar()
            observed["idle_in_transaction"] = probe.execute(text(IDLE_IN_TRANSACTION)).scalar()
        return [article(1)], SourceResult(name, "rss", True, 1, 0.0)

    session.rollback()  # the test's own session must not look like an open transaction
    outcome = RssIngestor(migrated_engine, fetch=slow_download).ingest(source)

    assert outcome.status == "succeeded"
    assert observed["locks"] == 1  # this source is protected during the HTTP request ...
    assert observed["idle_in_transaction"] == 0  # ... without holding a transaction open
