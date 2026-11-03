"""The article pipeline against PostgreSQL: screen -> fetch -> redact -> extract -> candidate.

Fetching and the AI are replaced by small fakes so nothing touches the network or costs
money; one end-to-end test runs the real RSS parser, the real article fetcher (against a
local server) and the real OpenAI client wrapper (with a fake SDK client).
All text and identifiers are synthetic.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text

import db_factories as f
from app.ingestion.article import ArticleFetcher, ArticleFetchError, ArticleText
from app.jobs import rss_poll
from app.models import AuditEvent, ExtractionRun, Incident, IncidentEvidence, SourceItem
from app.schemas.extraction import ExtractionResult
from app.services.extraction import (
    PROMPT_VERSION,
    ExtractionError,
    ExtractionOutput,
    ExtractorUnavailable,
    OpenAIExtractor,
)
from app.services.pipeline import LOCK_KEY, PipelineRunner, PipelineSummary
from feed_server import article_page, rss_document
from test_pipeline_units import FakeCompletions, fake_client, valid_reply

pytestmark = pytest.mark.usefixtures("migrated_engine")

PUBLISHED = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
BODY = (
    "A kombi overturned near Rusape on Sunday morning, killing five passengers. The deceased, "
    "Tendai Chuma, was driving ABC 1234. Police on 0772 123 456 confirmed the crash on the "
    "Harare-Mutare road and said investigations continue into the cause of the accident. "
) * 2


class FakeFetch:
    """Stands in for ArticleFetcher: url -> ArticleText, or an exception to raise."""

    def __init__(self, pages: dict | None = None, default: str | Exception = BODY):
        self.pages, self.default, self.calls = pages or {}, default, []

    def __call__(self, url: str) -> ArticleText:
        self.calls.append(url)
        outcome = self.pages.get(url, self.default)
        if isinstance(outcome, Exception):
            raise outcome
        return ArticleText(url=url, text=outcome, word_count=len(outcome.split()))


class FakeExtractor:
    model_name = "fake-model"

    def __init__(self, *replies, on_call=None):
        self.replies, self.calls, self.on_call = list(replies), [], on_call

    def extract(self, item):
        self.calls.append(item)
        if self.on_call:
            self.on_call(item)
        reply = self.replies.pop(0) if self.replies else result()
        if isinstance(reply, Exception):
            raise reply
        return ExtractionOutput(reply, "fake-model-1", PROMPT_VERSION, 100, 20)


def result(**overrides) -> ExtractionResult:
    return ExtractionResult.model_validate(valid_reply(**overrides))


def add_item(session, source=None, *, title="Kombi overturns near Rusape", excerpt="Five killed as a kombi overturned.",
             url=None, **overrides) -> SourceItem:
    source = source or f.make_source(session)
    url = url or f"https://news.example.test/{uuid.uuid4().hex[:10]}"
    item = f.make_source_item(
        session, source, title_redacted=title, excerpt_redacted=excerpt, canonical_url=url,
        published_at=PUBLISHED, source_metadata={"url": url, "redaction": "not_applied"}, **overrides,
    )
    session.commit()
    return item


def runner(engine, fetch=None, extractor=None, **kwargs) -> PipelineRunner:
    return PipelineRunner(engine, fetch_article=fetch or FakeFetch(), extractor=extractor, **kwargs)


def status(session, item) -> str:
    session.refresh(item)
    return item.processing_status


def count(session, model) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(model))


# --- stage 1: screening ----------------------------------------------------------------------


def test_irrelevant_items_are_filtered_and_never_fetched_or_sent_to_the_ai(session, migrated_engine):
    item = add_item(session, title="Warriors name squad for AFCON qualifier", excerpt="Coach names 23 players.")
    fetch, extractor = FakeFetch(), FakeExtractor()

    summary = runner(migrated_engine, fetch, extractor).run()

    assert status(session, item) == "filtered" and item.screen_reason.startswith("no road-incident")
    assert (summary.filtered, summary.screened, fetch.calls, extractor.calls) == (1, 0, [], [])


def test_screening_redacts_the_headline_and_excerpt(session, migrated_engine):
    item = add_item(session, title="John Moyo (34) dies in crash", excerpt="Call 0772 123 456 for the kombi accident.")

    summary = PipelineSummary()
    runner(migrated_engine, FakeFetch(), None).screen_pending(summary)

    session.refresh(item)
    assert "Moyo" not in item.title_redacted and "0772" not in item.excerpt_redacted
    assert item.source_metadata["redaction"] == "applied" and summary.screened == 1


# --- stage 2: fetching the full article ------------------------------------------------------


def test_the_full_article_is_fetched_redacted_and_stored(session, migrated_engine):
    item = add_item(session)
    runner(migrated_engine, FakeFetch(), None).run()

    session.refresh(item)
    assert item.processing_status == "fetched" and item.fetch_status == "ok" and item.fetched_at
    assert "overturned near Rusape" in item.article_text_redacted
    for private in ("Tendai Chuma", "ABC 1234", "0772 123 456"):
        assert private not in item.article_text_redacted
    assert len(item.content_hash) == 64
    counts = item.source_metadata["redaction_counts"]
    assert counts["phone"] == 2 and counts["plate"] == 2 and counts["name"] >= 2  # BODY is repeated twice


def test_the_article_url_comes_from_the_stored_item(session, migrated_engine):
    item = add_item(session, url="https://news.example.test/the-story")
    fetch = FakeFetch()
    runner(migrated_engine, fetch, None).run()
    assert fetch.calls == ["https://news.example.test/the-story"]
    assert status(session, item) == "fetched"


def test_an_unreadable_article_fails_closed_and_is_never_sent_to_the_ai(session, migrated_engine):
    item = add_item(session)
    fetch = FakeFetch(default=ArticleFetchError("HTTP 404"))
    extractor = FakeExtractor()

    summary = runner(migrated_engine, fetch, extractor).run()

    session.refresh(item)
    assert item.processing_status == "fetch_failed" and item.fetch_status == "failed"
    assert "404" in item.fetch_error and item.article_text_redacted is None
    assert extractor.calls == [] and summary.fetch_failed == 1 and count(session, Incident) == 0


def test_the_ai_never_falls_back_to_title_and_excerpt_alone(session, migrated_engine):
    add_item(session)
    extractor = FakeExtractor()
    runner(migrated_engine, FakeFetch(default=ArticleFetchError("paywall")), extractor).run()
    assert extractor.calls == []


def test_a_transient_failure_is_retried_next_cycle_then_given_up(session, migrated_engine):
    item = add_item(session)
    fetch = FakeFetch(default=ArticleFetchError("timed out", transient=True))
    r = runner(migrated_engine, fetch, None, max_attempts=3)

    r.run()
    assert status(session, item) == "screened" and item.source_metadata["fetch_attempts"] == 1
    r.run()
    assert status(session, item) == "screened"
    summary = r.run()
    assert status(session, item) == "fetch_failed" and summary.fetch_failed == 1
    assert len(fetch.calls) == 3


def test_an_unexpected_error_in_the_fetcher_is_contained(session, migrated_engine):
    bad, good = add_item(session, url="https://news.example.test/bad"), add_item(session, url="https://news.example.test/good")
    fetch = FakeFetch({"https://news.example.test/bad": RuntimeError("parser exploded")})
    runner(migrated_engine, fetch, None).run()
    assert status(session, bad) == "fetch_failed" and status(session, good) == "fetched"


def test_an_item_without_any_url_cannot_be_fetched(session, migrated_engine):
    source = f.make_source(session)
    item = f.make_source_item(session, source, canonical_url=None, external_id="guid-only",
                              title_redacted="Kombi crash", excerpt_redacted="accident", source_metadata={})
    session.commit()
    runner(migrated_engine, FakeFetch(), None).run()
    session.refresh(item)
    assert item.processing_status == "fetch_failed" and "no article URL" in item.fetch_error


def test_each_stage_respects_the_batch_size(session, migrated_engine):
    items = [add_item(session) for _ in range(5)]
    r = runner(migrated_engine, FakeFetch(), None, batch_size=2)
    r.run()
    assert [status(session, i) for i in items].count("fetched") == 2
    r.run()
    assert [status(session, i) for i in items].count("fetched") == 4


# --- stage 3: extraction and candidates -------------------------------------------------------


def test_a_relevant_article_becomes_a_candidate_incident_with_evidence_and_an_audit_trail(session, migrated_engine):
    source = f.make_source(session)
    source.verification_tier = "established_media"
    item = add_item(session, source)
    extractor = FakeExtractor(result(severity="fatal", confidence=0.9))

    summary = runner(migrated_engine, FakeFetch(), extractor).run()

    session.expire_all()
    incident = session.scalars(select(Incident)).one()
    assert incident.status == "candidate"  # a human must still review it
    assert incident.incident_type == "rollover" and incident.severity == "fatal"
    assert incident.location_text == "Harare-Mutare road near Rusape"
    assert incident.occurred_at == datetime(2026, 11, 2, 3, 30, tzinfo=UTC)
    assert incident.credibility_score == 0.81  # 0.9 confidence x 0.9 established media
    assert incident.review_priority == "high"
    assert incident.reference_code.startswith("SRZ-20261102-")

    evidence = session.scalars(select(IncidentEvidence)).one()
    assert (evidence.incident_id, evidence.source_item_id, evidence.evidence_role) == (incident.id, item.id, "primary")

    run = session.scalars(select(ExtractionRun)).one()
    assert run.status == "succeeded" and run.model_name == "fake-model-1" and run.prompt_version == PROMPT_VERSION
    assert (run.input_tokens, run.output_tokens, run.extraction_confidence) == (100, 20, 0.9)
    assert run.extraction_output["incident_type"] == "rollover" and run.completed_at

    audit = session.scalars(select(AuditEvent)).one()
    assert (audit.action, audit.entity_id, audit.actor_user_id) == ("incident.candidate_created", incident.id, None)
    assert audit.details["extraction_run_id"] == str(run.id)

    assert status(session, item) == "processed"
    assert (summary.extracted, summary.incidents_created) == (1, 1)


def test_the_ai_receives_the_full_redacted_article_not_just_the_headline(session, migrated_engine):
    add_item(session, title="Kombi overturns near Rusape", excerpt="Short excerpt only.")
    extractor = FakeExtractor()
    runner(migrated_engine, FakeFetch(), extractor).run()

    sent = extractor.calls[0]
    assert "Police on [PHONE] confirmed the crash" in sent.text and len(sent.text) > 400
    assert "Short excerpt only" not in sent.text
    for private in ("Tendai Chuma", "ABC 1234", "0772 123 456"):
        assert private not in sent.text and private not in sent.title
    assert sent.published == PUBLISHED


def test_an_article_that_is_not_a_road_incident_is_discarded(session, migrated_engine):
    item = add_item(session)
    runner(migrated_engine, FakeFetch(), FakeExtractor(result(is_road_incident=False, confidence=0.95))).run()
    session.refresh(item)
    assert item.processing_status == "discarded" and item.source_metadata["discard_reason"] == "not_a_road_incident"
    assert count(session, Incident) == 0 and count(session, ExtractionRun) == 1


def test_low_confidence_is_discarded_for_review_tooling_not_published(session, migrated_engine):
    item = add_item(session)
    runner(migrated_engine, FakeFetch(), FakeExtractor(result(confidence=0.4)), min_confidence=0.6).run()
    session.refresh(item)
    assert item.processing_status == "discarded" and item.source_metadata["discard_reason"] == "low_confidence"
    assert count(session, Incident) == 0


def test_a_retryable_extraction_error_is_retried_then_given_up(session, migrated_engine):
    item = add_item(session)
    extractor = FakeExtractor(*[ExtractionError("timeout")] * 5)
    r = runner(migrated_engine, FakeFetch(), extractor, max_attempts=3)

    r.run()
    assert status(session, item) == "fetched"
    r.run()
    assert status(session, item) == "fetched"
    summary = r.run()
    assert status(session, item) == "failed" and summary.extraction_failed == 1
    assert count(session, ExtractionRun) == 3
    assert {run.status for run in session.scalars(select(ExtractionRun))} == {"failed"}
    assert count(session, Incident) == 0


def test_a_non_retryable_error_fails_the_item_immediately(session, migrated_engine):
    item = add_item(session)
    runner(migrated_engine, FakeFetch(), FakeExtractor(ExtractionError("refused", retryable=False))).run()
    assert status(session, item) == "failed"


def test_rejected_credentials_stop_the_batch_without_blaming_the_articles(session, migrated_engine):
    items = [add_item(session) for _ in range(3)]
    extractor = FakeExtractor(ExtractorUnavailable("bad key"))

    summary = runner(migrated_engine, FakeFetch(), extractor).run()

    assert len(extractor.calls) == 1  # stopped after the first rejection
    assert [status(session, i) for i in items] == ["fetched"] * 3  # still waiting for a working key
    assert count(session, ExtractionRun) == 0 and "credentials" in summary.extraction_skipped


def test_without_an_extractor_articles_are_still_screened_and_fetched(session, migrated_engine):
    item = add_item(session)
    summary = runner(migrated_engine, FakeFetch(), None).run()
    assert status(session, item) == "fetched" and "OPENAI_API_KEY" in summary.extraction_skipped
    assert count(session, ExtractionRun) == 0


def test_articles_fetched_earlier_are_extracted_once_a_key_is_configured(session, migrated_engine):
    item = add_item(session)
    runner(migrated_engine, FakeFetch(), None).run()
    runner(migrated_engine, FakeFetch(), FakeExtractor()).run()
    assert status(session, item) == "processed"


def test_running_again_never_repeats_work_or_duplicates_incidents(session, migrated_engine):
    add_item(session)
    fetch, extractor = FakeFetch(), FakeExtractor()
    r = runner(migrated_engine, fetch, extractor)
    r.run()
    again = r.run()
    assert len(fetch.calls) == 1 and len(extractor.calls) == 1
    assert count(session, Incident) == count(session, ExtractionRun) == 1
    assert (again.screened, again.fetched, again.extracted) == (0, 0, 0)


def test_two_reports_of_the_same_event_share_one_incident(session, migrated_engine):
    first = add_item(session)
    runner(migrated_engine, FakeFetch(default=BODY), FakeExtractor(result(confidence=0.8))).run()
    second = add_item(session)  # a later report of the same event
    second_body = BODY.replace("Sunday morning", "Sunday")  # a different publisher's wording
    runner(migrated_engine, FakeFetch(default=second_body), FakeExtractor(result(confidence=0.8))).run()

    session.expire_all()
    assert count(session, Incident) == 1
    roles = sorted(e.evidence_role for e in session.scalars(select(IncidentEvidence)))
    assert roles == ["corroborating", "primary"]
    assert {status(session, first), status(session, second)} == {"processed"}
    incident = session.scalars(select(Incident)).one()
    assert incident.credibility_score > round(0.8 * 0.5, 2)  # corroboration raised it
    assert incident.status == "candidate"
    assert sorted(a.action for a in session.scalars(select(AuditEvent))) == [
        "incident.candidate_created", "incident.evidence_added",
    ]


def test_different_places_or_types_are_separate_incidents(session, migrated_engine):
    items = [add_item(session) for _ in range(3)]
    # distinct text per article, so these are not mistaken for syndicated copies
    fetch = FakeFetch({i.canonical_url: BODY + f" Report number {n}." for n, i in enumerate(items)})
    replies = [
        result(location_text="Rusape"),
        result(location_text="Beitbridge"),
        result(location_text="Rusape", incident_type="collision"),
    ]
    runner(migrated_engine, fetch, FakeExtractor(*replies), batch_size=5).run()
    assert count(session, Incident) == 3


def test_syndicated_copies_are_extracted_only_once(session, migrated_engine):
    a, b = add_item(session), add_item(session)  # same text published under two sources
    extractor = FakeExtractor()
    runner(migrated_engine, FakeFetch(default=BODY), extractor).run()

    assert len(extractor.calls) == 1
    session.expire_all()
    statuses = {status(session, a), status(session, b)}
    assert statuses == {"processed", "discarded"}
    discarded = a if a.processing_status == "discarded" else b
    assert discarded.source_metadata["discard_reason"].startswith("duplicate_content_of:")
    assert count(session, Incident) == 1


def test_an_item_that_changed_while_the_ai_was_working_is_not_overwritten(session, migrated_engine):
    item = add_item(session)

    def editor_discards_it_meanwhile(_):
        with migrated_engine.begin() as conn:
            conn.execute(text("UPDATE source_items SET processing_status = 'discarded' WHERE id = :i"), {"i": item.id})

    runner(migrated_engine, FakeFetch(), FakeExtractor(on_call=editor_discards_it_meanwhile)).run()

    assert status(session, item) == "discarded"
    assert count(session, Incident) == 0 and count(session, ExtractionRun) == 0


def test_the_pipeline_never_approves_or_publishes(session, migrated_engine):
    for _ in range(4):
        add_item(session)
    runner(migrated_engine, FakeFetch(), FakeExtractor(result(severity="fatal", confidence=1.0)), batch_size=10).run()
    session.expire_all()
    assert {i.status for i in session.scalars(select(Incident))} == {"candidate"}
    assert count(session, Incident) >= 1


def test_a_second_pipeline_process_is_locked_out(session, migrated_engine):
    add_item(session)
    holder = migrated_engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        assert holder.execute(text("SELECT pg_try_advisory_lock(CAST(:k AS BIGINT))"), {"k": LOCK_KEY}).scalar()
        fetch = FakeFetch()
        summary = runner(migrated_engine, fetch, None).run()
        assert summary.skipped_locked and fetch.calls == []
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"), {"k": LOCK_KEY})
        holder.close()
    assert not runner(migrated_engine, FakeFetch(), None).run().skipped_locked  # released: runs again


def test_the_lock_is_released_even_when_a_stage_blows_up(session, migrated_engine, monkeypatch):
    r = runner(migrated_engine, FakeFetch(), None)
    monkeypatch.setattr(r, "screen_pending", lambda summary: (_ for _ in ()).throw(RuntimeError("db down")))
    with pytest.raises(RuntimeError):
        r.run()
    assert not runner(migrated_engine, FakeFetch(), None).run().skipped_locked


def test_concurrent_runners_do_not_double_process(session, migrated_engine):
    for _ in range(6):
        add_item(session)
    extractor = FakeExtractor()
    barrier = threading.Barrier(2)

    def go():
        barrier.wait()
        runner(migrated_engine, FakeFetch(), extractor, batch_size=10).run()

    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(extractor.calls) <= 6
    assert count(session, ExtractionRun) == len(extractor.calls)


# --- end to end ------------------------------------------------------------------------------


def test_end_to_end_rss_feed_to_candidate_incident(session, migrated_engine, feed_server):
    """Real RSS parser -> DB -> real article fetcher (local server) -> real OpenAI wrapper (fake SDK)."""
    source = f.make_source(session)
    source.verification_tier = "established_media"
    page_url = feed_server.serve_html("/news/kombi-crash", article_page("Kombi overturns near Rusape", [BODY, BODY]))
    other_url = feed_server.serve_html("/news/budget", article_page("Budget speech", ["Finance minister presents the budget. " * 30]))
    source.feed_url = feed_server.serve("/feed", rss_document([
        {"title": "Kombi overturns near Rusape", "link": page_url, "guid": "g1", "summary": "Five killed in a crash."},
        {"title": "Finance minister presents budget", "link": other_url, "guid": "g2", "summary": "Taxes and spending."},
    ]))
    session.commit()

    poll = rss_poll.poll_sources(migrated_engine)
    assert poll.inserted == 2

    completions = FakeCompletions(valid_reply(confidence=0.92))
    extractor = OpenAIExtractor(fake_client(completions), model="gpt-4o-mini")
    fetcher = ArticleFetcher(allow_private_hosts=True, delay=0, min_words=40)
    summary = PipelineRunner(migrated_engine, fetch_article=fetcher, extractor=extractor).run()

    assert (summary.filtered, summary.screened, summary.fetched, summary.incidents_created) == (1, 1, 1, 1)
    assert feed_server.hits["/news/kombi-crash"] == 1 and feed_server.hits["/news/budget"] == 0
    assert len(completions.calls) == 1
    prompt = completions.calls[0]["messages"][1]["content"]
    assert "overturned near Rusape" in prompt and "Tendai Chuma" not in prompt and "0772" not in prompt
    session.expire_all()
    assert session.scalars(select(Incident)).one().status == "candidate"
    items = {i.title_redacted: i.processing_status for i in session.scalars(select(SourceItem))}
    assert items == {"Kombi overturns near Rusape": "processed", "Finance minister presents budget": "filtered"}
