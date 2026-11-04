"""Social ingestion against PostgreSQL: allowlist, quarantine, cost guards, and the hand-off to the
shared article pipeline. Apify is replaced by a fake runner, so nothing leaves the machine.
All accounts, ids and text are synthetic.
"""

import textwrap
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update

from app.core.config import Settings
from app.ingestion.rss import SKIPPED
from app.ingestion.social.poller import SocialIngestor, social_lock_key
from app.ingestion.social.runner import ActorRunError, apify_actor_path
from app.ingestion.social.seed import SocialSourceConfig, load_config, sync_social_sources
from app.jobs.social_poll import poll_social
from app.models import (
    ExtractionRun,
    Incident,
    IncidentEvidence,
    IngestionRun,
    SocialQuarantine,
    SocialSource,
    Source,
    SourceItem,
)
from app.models.enums import CollectionStatus, IngestionStatus, ProcessingStatus
from app.services.pipeline import PipelineRunner
import db_factories as f
from test_article_pipeline import FakeExtractor, FakeFetch, result

pytestmark = pytest.mark.usefixtures("migrated_engine")

PAGE = "https://www.facebook.com/roadwatchzw"
ACTOR = "neverempty/facebook-page-posts-scraper"
NOW = datetime.now(UTC)


class FakeRunner:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows, self.error, self.calls = rows or [], error, []

    def run(self, actor_id, run_input, *, max_items, timeout_seconds, max_charge_usd):
        self.calls.append(
            dict(actor_id=actor_id, run_input=run_input, max_items=max_items, timeout=timeout_seconds, charge=max_charge_usd)
        )
        if self.error:
            raise self.error
        return list(self.rows)


def post(post_id="9001", **overrides) -> dict:
    item = {
        "dataType": "post", "facebookUrl": PAGE, "postId": post_id, "url": f"{PAGE}/posts/{post_id}",
        "time": (NOW - timedelta(hours=1)).isoformat(),
        "text": "Kombi overturned near Rusape on the Harare-Mutare road, five people injured.",
        "pageId": "555", "pageUrl": PAGE, "pageName": "Road Watch",
    }
    item.update(overrides)
    return item


def make_source(session, name="Road Watch", **overrides):
    config = dict(
        name=name, platform="facebook", account_url=PAGE, actor_id=ACTOR, enabled=True,
        poll_interval_minutes=120, max_posts_per_run=5,
    )
    config.update(overrides)
    outcome = sync_social_sources(session, [SocialSourceConfig(**config)])
    assert not outcome.errors
    session.commit()
    return session.scalar(select(Source).where(Source.name == name))


def state_of(session, source):
    session.expire_all()
    return session.scalar(select(SocialSource).where(SocialSource.source_id == source.id))


def ingestor(engine, runner, **kwargs) -> SocialIngestor:
    return SocialIngestor(engine, runner, **kwargs)


def items(session):
    session.expire_all()
    return session.scalars(select(SourceItem).order_by(SourceItem.external_id)).all()


# -- storing ---------------------------------------------------------------------
def test_accepted_posts_become_pending_source_items(migrated_engine, session):
    source = make_source(session)
    runner = FakeRunner([post("1"), post("2", time="2026-01-01T00:00:00Z")])

    outcome = ingestor(migrated_engine, runner).ingest(source.id)

    assert (outcome.status, outcome.fetched, outcome.inserted, outcome.duplicates) == ("succeeded", 2, 2, 0)
    stored = items(session)
    assert [i.external_id for i in stored] == ["facebook:1", "facebook:2"]
    first = stored[0]
    assert first.processing_status == ProcessingStatus.PENDING.value
    assert first.canonical_url == f"{PAGE}/posts/1"
    assert first.source_metadata["content_kind"] == "social_post"
    assert first.source_metadata["redaction"] == "not_applied"
    assert "likes" not in first.source_metadata
    assert first.excerpt_redacted.startswith("Kombi overturned")

    run = session.scalars(select(IngestionRun)).one()
    assert (run.status, run.fetched_count, run.inserted_count) == ("succeeded", 2, 2)
    state = state_of(session, source)
    assert state.collection_status == CollectionStatus.OK.value
    assert state.last_polled_at and state.last_success_at
    assert state.last_post_id == "facebook:1"  # the newest accepted post is the cursor
    assert state.platform_account_id == "555"  # pinned from the first verified post


def test_the_actor_is_asked_for_one_page_with_a_spend_ceiling(migrated_engine, session):
    source = make_source(session, max_posts_per_run=4)
    runner = FakeRunner([post()])
    ingestor(migrated_engine, runner, max_charge_usd=0.1, run_timeout_seconds=300).ingest(source.id)
    call = runner.calls[0]
    assert call["actor_id"] == ACTOR
    assert call["run_input"]["startUrls"] == [PAGE]
    assert call["run_input"]["resultsLimit"] == 4 and call["run_input"]["onlyPostsNewerThan"] == "48 hours"
    assert (call["max_items"], call["timeout"], call["charge"]) == (4, 300, 0.1)


def test_repeated_posts_are_not_stored_twice(migrated_engine, session):
    source = make_source(session)
    runner = FakeRunner([post("1"), post("2")])
    ing = ingestor(migrated_engine, runner)
    ing.ingest(source.id)
    again = ing.ingest(source.id, force=True)
    assert (again.inserted, again.duplicates) == (0, 2)
    assert len(items(session)) == 2


def test_more_posts_than_the_cap_are_ignored(migrated_engine, session):
    source = make_source(session, max_posts_per_run=2)
    ingestor(migrated_engine, FakeRunner([post(str(n)) for n in range(1, 6)])).ingest(source.id)
    assert len(items(session)) == 2


# -- allowlist -------------------------------------------------------------------
def test_foreign_posts_are_dropped_and_doubtful_ones_quarantined(migrated_engine, session):
    source = make_source(session)
    rows = [
        post("1"),
        post("2", pageId="777", pageUrl="https://www.facebook.com/otherpage", url="https://www.facebook.com/otherpage/posts/2"),
        post("3", pageId=None, pageUrl=None, text="Secret details of a crash"),
    ]
    outcome = ingestor(migrated_engine, FakeRunner(rows)).ingest(source.id)

    assert outcome.status == IngestionStatus.PARTIAL.value
    assert (outcome.inserted, outcome.rejected, outcome.quarantined) == (1, 1, 1)
    assert [i.external_id for i in items(session)] == ["facebook:1"]
    held = session.scalars(select(SocialQuarantine)).one()
    assert (held.reason, held.external_id) == ("origin_unverifiable", "3")
    assert "Secret details" not in str(held.summary) and "Secret details" not in (held.post_url or "")
    run = session.scalars(select(IngestionRun)).one()
    assert "origin_unverifiable" in run.error_message and "origin_mismatch" in run.error_message


def test_once_the_account_id_is_known_a_lookalike_page_is_rejected(migrated_engine, session):
    source = make_source(session, platform_account_id="555")
    spoof = post("1", pageId="999")  # same address on the post, different Page id
    outcome = ingestor(migrated_engine, FakeRunner([spoof])).ingest(source.id)
    assert (outcome.inserted, outcome.rejected) == (0, 1)


def test_disabled_sources_are_never_polled(migrated_engine, session):
    source = make_source(session, enabled=False)
    runner = FakeRunner([post()])
    outcome = ingestor(migrated_engine, runner).ingest(source.id)
    assert outcome.status == SKIPPED and runner.calls == []
    assert ingestor(migrated_engine, runner).due_sources() == []


def test_a_platform_without_an_adapter_is_never_polled(migrated_engine, session):
    source = make_source(session, name="X desk", platform="facebook")
    session.execute(update(SocialSource).where(SocialSource.source_id == source.id).values(platform="x"))
    session.commit()
    runner = FakeRunner([post()])
    outcome = ingestor(migrated_engine, runner).ingest(source.id, force=True)
    assert outcome.status == SKIPPED and "not supported" in outcome.error and runner.calls == []


def test_a_source_that_is_not_on_the_allowlist_is_not_polled(migrated_engine, session):
    rss = f.make_source(session, kind="rss")
    session.commit()
    runner = FakeRunner([post()])
    outcome = ingestor(migrated_engine, runner).ingest(rss.id, force=True)
    assert outcome.status == SKIPPED and runner.calls == []


# -- schedule and budget ---------------------------------------------------------
def test_an_account_is_polled_only_when_its_interval_has_elapsed(migrated_engine, session):
    source = make_source(session)
    runner = FakeRunner([post()])
    ing = ingestor(migrated_engine, runner)
    assert [s.source_id for s in ing.due_sources()] == [source.id]
    ing.ingest(source.id)
    assert ing.due_sources() == []
    skipped = ing.ingest(source.id)
    assert skipped.status == SKIPPED and len(runner.calls) == 1
    assert [s.source_id for s in ing.due_sources(datetime.now(UTC) + timedelta(minutes=121))] == [source.id]


def test_the_daily_run_budget_stops_further_polls(migrated_engine, session):
    first, second = make_source(session, "First"), make_source(session, "Second", account_url=PAGE + "two")
    runner = FakeRunner([post()])
    ing = ingestor(migrated_engine, runner, max_runs_per_day=1)
    assert ing.ingest(first.id).status == "succeeded"
    blocked = ing.ingest(second.id)
    assert blocked.status == SKIPPED and "budget" in blocked.error
    assert len(runner.calls) == 1


def test_a_failed_poll_is_recorded_and_retried_sooner(migrated_engine, session):
    source = make_source(session)
    boom = ActorRunError("Actor run abc ended with status FAILED")
    ing = ingestor(migrated_engine, FakeRunner(error=boom), retry_after_error=timedelta(minutes=30))
    outcome = ing.ingest(source.id)
    assert outcome.status == "failed" and "FAILED" in outcome.error
    run = session.scalars(select(IngestionRun)).one()
    assert run.status == "failed" and run.completed_at is not None
    state = state_of(session, source)
    assert state.collection_status == CollectionStatus.ERROR.value and "FAILED" in state.last_error
    assert state.last_success_at is None
    assert ing.due_sources() == []
    assert [s.source_id for s in ing.due_sources(datetime.now(UTC) + timedelta(minutes=31))] == [source.id]


def test_errors_never_store_secrets(migrated_engine, session):
    source = make_source(session)
    error = RuntimeError("request to https://api.apify.com/x?token=apify_api_SECRET123 failed")
    ingestor(migrated_engine, FakeRunner(error=error)).ingest(source.id)
    session.expire_all()
    assert "SECRET123" not in session.scalars(select(IngestionRun)).one().error_message
    assert "SECRET123" not in state_of(session, source).last_error


def test_a_page_facebook_will_not_show_marks_the_source_blocked(migrated_engine, session):
    source = make_source(session)
    note = {"dataType": "note", "reason": "not-found", "message": "Page is not shown to visitors"}
    outcome = ingestor(migrated_engine, FakeRunner([note])).ingest(source.id)
    assert outcome.status == "failed"
    state = state_of(session, source)
    assert state.collection_status == CollectionStatus.BLOCKED.value and "not-found" in state.last_error
    assert state.last_success_at is None


def test_a_quiet_page_is_a_success_not_an_error(migrated_engine, session):
    source = make_source(session)
    note = {"dataType": "note", "reason": "no-posts-in-range", "message": "nothing new"}
    outcome = ingestor(migrated_engine, FakeRunner([note])).ingest(source.id)
    assert (outcome.status, outcome.fetched, outcome.inserted) == ("succeeded", 0, 0)
    assert state_of(session, source).collection_status == CollectionStatus.OK.value


def test_two_workers_cannot_poll_the_same_account(migrated_engine, session):
    source = make_source(session)
    runner = FakeRunner([post()])
    with migrated_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as other:
        other.execute(text("SELECT pg_advisory_lock(CAST(:k AS BIGINT))"), {"k": social_lock_key(source.id)})
        try:
            outcome = ingestor(migrated_engine, runner).ingest(source.id)
        finally:
            other.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"), {"k": social_lock_key(source.id)})
    assert outcome.status == SKIPPED and runner.calls == []


# -- the scheduled entry point ---------------------------------------------------
def test_polling_needs_a_token_and_polls_only_due_accounts(migrated_engine, session):
    make_source(session)
    no_token = Settings(_env_file=None, apify_api_token=None)
    assert poll_social(migrated_engine, no_token) == []

    settings = Settings(_env_file=None, apify_api_token="tok")
    runner = FakeRunner([post()])
    assert [o.status for o in poll_social(migrated_engine, settings, runner=runner)] == ["succeeded"]
    assert poll_social(migrated_engine, settings, runner=runner) == []  # nothing is due any more
    assert len(runner.calls) == 1


# -- the allowlist file ----------------------------------------------------------
def write_yaml(tmp_path, body: str):
    path = tmp_path / "social.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def test_config_rejects_unverified_or_unsupported_entries(tmp_path):
    path = write_yaml(
        tmp_path,
        f"""
        social_sources:
          - {{name: "Placeholder", platform: facebook, account_url: "<verified-facebook-page-url>", actor_id: "{ACTOR}"}}
          - {{name: "Traffic on X", platform: x, account_url: "https://x.com/someone", actor_id: "o/a", enabled: true}}
          - {{name: "Frequent", platform: facebook, account_url: "{PAGE}", actor_id: "{ACTOR}", poll_interval_minutes: 1}}
          - {{name: "Group", platform: facebook, account_url: "https://www.facebook.com/groups/1", actor_id: "{ACTOR}"}}
          - {{name: "Typo", platform: facebook, account_url: "{PAGE}", actor_id: "{ACTOR}", enable: true}}
          - {{name: "X disabled is fine", platform: x, account_url: "https://x.com/someone", actor_id: "o/a", enabled: false}}
          - {{name: "Good", platform: facebook, account_url: "{PAGE}/", actor_id: "{ACTOR}"}}
        """,
    )
    configs, errors = load_config(path)
    assert [c.name for c in configs] == ["X disabled is fine", "Good"]
    assert len(errors) == 5
    assert any("not available yet" in e for e in errors)
    assert configs[1].account_url == PAGE and configs[1].enabled is False  # canonical, off by default


def test_the_shipped_config_is_valid():
    configs, errors = load_config()
    assert errors == [] and len(configs) <= 10


def test_syncing_config_keeps_collection_state(migrated_engine, session):
    source = make_source(session)
    ingestor(migrated_engine, FakeRunner([post()])).ingest(source.id)
    session.expire_all()
    before = state_of(session, source)
    cursor, pinned, polled = before.last_post_id, before.platform_account_id, before.last_polled_at

    make_source(session, poll_interval_minutes=240, max_posts_per_run=3)
    session.expire_all()
    after = state_of(session, source)
    assert (after.max_posts_per_run, session.get(Source, source.id).poll_interval_seconds) == (3, 14400)
    assert (after.last_post_id, after.platform_account_id, after.last_polled_at) == (cursor, pinned, polled)

    make_source(session, account_url="https://www.facebook.com/anotherpage")  # a different account
    session.expire_all()
    changed = state_of(session, source)
    assert changed.platform_account_id is None and changed.last_post_id is None


def test_apify_actor_ids_use_the_rest_form():
    assert apify_actor_path(ACTOR) == "neverempty~facebook-page-posts-scraper"


# -- hand-off to the shared pipeline ---------------------------------------------
def pipeline(engine, fetch, extractor):
    return PipelineRunner(engine, fetch_article=fetch, extractor=extractor, batch_size=10)


def test_a_social_post_reaches_a_candidate_incident_without_fetching_any_page(migrated_engine, session):
    source = make_source(session)
    text_in = "Kombi overturned near Rusape. Call Tendai on 0772 123 456."
    ingestor(migrated_engine, FakeRunner([post("1", text=text_in)])).ingest(source.id)
    fetch, extractor = FakeFetch(), FakeExtractor(result())

    summary = pipeline(migrated_engine, fetch, extractor).run()

    assert fetch.calls == []  # no article retrieval for a plain post
    assert (summary.screened, summary.fetched, summary.incidents_created) == (1, 1, 1)
    item = items(session)[0]
    assert item.processing_status == ProcessingStatus.PROCESSED.value
    assert "0772" not in item.article_text_redacted and "0772" not in extractor.calls[0].text  # redacted before the AI
    assert item.content_hash and item.fetch_status == "ok"
    assert extractor.calls[0].source_name == "Road Watch"
    incident = session.scalars(select(Incident)).one()
    assert incident.status == "candidate"
    assert session.scalars(select(IncidentEvidence)).one().source_item_id == item.id


def test_irrelevant_posts_are_filtered_before_the_ai(migrated_engine, session):
    source = make_source(session)
    ingestor(migrated_engine, FakeRunner([post("1", text="Happy Independence Day from all of us!")])).ingest(source.id)
    extractor = FakeExtractor()
    pipeline(migrated_engine, FakeFetch(), extractor).run()
    assert items(session)[0].processing_status == ProcessingStatus.FILTERED.value
    assert extractor.calls == []


def test_a_post_linking_to_an_article_is_read_together_with_it(migrated_engine, session):
    source = make_source(session)
    link = "https://news.example.org/rusape-crash"
    ingestor(migrated_engine, FakeRunner([post("1", link=link)])).ingest(source.id)
    fetch = FakeFetch({link: "Full article: police say the kombi overturned after a tyre burst. " * 5})
    extractor = FakeExtractor(result())

    pipeline(migrated_engine, fetch, extractor).run()

    assert fetch.calls == [link]
    text_sent = extractor.calls[0].text
    assert text_sent.startswith("Kombi overturned") and "tyre burst" in text_sent


def test_an_unreadable_linked_article_falls_back_to_the_post(migrated_engine, session):
    from app.ingestion.article import ArticleFetchError

    source = make_source(session)
    link = "https://news.example.org/gone"
    ingestor(migrated_engine, FakeRunner([post("1", link=link)])).ingest(source.id)
    fetch = FakeFetch({link: ArticleFetchError("HTTP 404", transient=False)})
    extractor = FakeExtractor(result())

    summary = pipeline(migrated_engine, fetch, extractor).run()

    assert summary.fetch_failed == 0 and summary.incidents_created == 1
    item = items(session)[0]
    assert item.processing_status == ProcessingStatus.PROCESSED.value
    assert item.source_metadata["linked_article"] == "unreadable"
    assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 1


def test_quarantined_posts_never_reach_the_pipeline(migrated_engine, session):
    source = make_source(session)
    ingestor(migrated_engine, FakeRunner([post("1", pageId=None, pageUrl=None)])).ingest(source.id)
    extractor = FakeExtractor()
    pipeline(migrated_engine, FakeFetch(), extractor).run()
    assert items(session) == [] and extractor.calls == []


def test_policy_limits_five_posts_per_page_and_ten_pages(tmp_path):
    entry = '  - {{name: "Page {n}", platform: facebook, account_url: "https://www.facebook.com/page{n}", actor_id: "{a}"}}'
    rows = [entry.format(n=n, a=ACTOR) for n in range(11)]
    over = write_yaml(tmp_path, "social_sources:" + chr(10) + chr(10).join(rows) + chr(10))
    configs, errors = load_config(over)
    assert len(configs) == 10 and "limited to 10" in errors[0]
    assert configs[0].max_posts_per_run == 5  # default
    greedy = '  - {{name: "Greedy", platform: facebook, account_url: "{u}", actor_id: "{a}", max_posts_per_run: 16}}'
    too_many = write_yaml(tmp_path, "social_sources:" + chr(10) + greedy.format(u=PAGE, a=ACTOR) + chr(10))
    assert load_config(too_many)[0] == []
