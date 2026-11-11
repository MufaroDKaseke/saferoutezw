"""NUST FM mode, pipeline: every article is kept and classified; no road screening, no incidents.

The classifier and article fetching are fakes: nothing touches the network or costs money.
"""

import pytest
from sqlalchemy import func, select

import db_factories as f
from app.ingestion.article import ArticleFetchError
from app.jobs import pipeline_job
from app.models import ExtractionRun, Incident, SourceItem
from app.models.enums import ProcessingStatus
from app.core.config import Settings
from app.services.pipeline import NEWSROOM_LOCK_KEY, LOCK_KEY, PipelineRunner
from newsroom_helpers import FakeNewsroomExtractor, classification, retryable_error
from test_article_pipeline import FakeFetch, add_item

pytestmark = pytest.mark.usefixtures("migrated_engine")

POLITICS = "The finance minister presented the national budget to Parliament on Thursday. " * 6
CAMPUS = "NUST announced new enrolment dates for the second semester and a revised fee schedule. " * 6
SPORT = "The Warriors beat their visitors two goals to one in a friendly played on Saturday. " * 6
CRASH = "A kombi overturned near Rusape on Sunday and five passengers were injured, police said. " * 6


def runner(engine, fetch=None, extractor=None, **kw):
    return PipelineRunner(engine, fetch_article=fetch or FakeFetch(), extractor=extractor, newsroom=True, **kw)


def status_of(session, item):
    session.refresh(item)
    return item.processing_status


def test_every_article_is_kept_whatever_it_is_about(session, migrated_engine):
    source = f.make_source(session)
    items = {
        "politics": add_item(session, source, title="Budget presented to Parliament", excerpt="The minister spoke.", url="https://n.test/politics"),
        "campus": add_item(session, source, title="NUST announces enrolment dates", excerpt="Second semester.", url="https://n.test/campus"),
        "sport": add_item(session, source, title="Warriors beat visitors", excerpt="Friendly match.", url="https://n.test/sport"),
        "crash": add_item(session, source, title="Kombi overturns near Rusape", excerpt="Five injured.", url="https://n.test/crash"),
    }
    pages = {"https://n.test/politics": POLITICS, "https://n.test/campus": CAMPUS,
             "https://n.test/sport": SPORT, "https://n.test/crash": CRASH}
    extractor = FakeNewsroomExtractor(
        classification(primary_category="politics_governance"),
        classification(primary_category="education", summary="NUST announced enrolment dates."),
        classification(primary_category="sports", summary="The Warriors won a friendly."),
        classification(primary_category="community_local", summary="A kombi overturned near Rusape."),
    )

    summary = runner(migrated_engine, FakeFetch(pages), extractor).run()
    session.expire_all()

    assert (summary.screened, summary.filtered, summary.fetched, summary.extracted) == (4, 0, 4, 4)
    for name, item in items.items():
        assert status_of(session, item) == "processed", name
        assert item.screen_reason == "newsroom: kept"
    categories = {i.source_metadata["classification"]["primary_category"] for i in items.values()}
    assert categories == {"politics_governance", "education", "sports", "community_local"}
    # A road accident is general news here: it never becomes an incident.
    assert session.scalar(select(func.count()).select_from(Incident)) == 0


def test_classification_and_usage_are_stored_without_a_migration(session, migrated_engine):
    item = add_item(session, title="Budget presented", excerpt="x")
    runner(migrated_engine, FakeFetch(default=POLITICS), FakeNewsroomExtractor(classification())).run()
    session.expire_all()
    cls = item.source_metadata["classification"]
    assert cls["summary"] == "Parliament debated the national budget."
    assert cls["basis"] == "full_text" and cls["model"] == "fake-newsroom-model-1" and cls["prompt_version"] == "newsroom-v1"
    run = session.scalars(select(ExtractionRun)).one()
    assert (run.status, run.prompt_version, run.input_tokens, run.output_tokens) == ("succeeded", "newsroom-v1", 120, 60)
    assert run.extraction_output["newsroom"]["primary_category"] == "politics_governance"
    assert cls["run_id"] == str(run.id)
    assert item.source_metadata["redaction"] == "applied"  # the model only ever sees redacted text


def test_identical_text_is_classified_once_and_both_articles_are_kept(session, migrated_engine):
    source = f.make_source(session)
    first = add_item(session, source, title="Budget (Herald)", url="https://n.test/a")
    second = add_item(session, source, title="Budget (syndicated copy)", url="https://n.test/b")
    extractor = FakeNewsroomExtractor(classification())
    summary = runner(migrated_engine, FakeFetch(default=POLITICS), extractor).run()
    session.expire_all()
    assert len(extractor.calls) == 1 and summary.reused == 1  # no second model call
    assert status_of(session, first) == "processed" and status_of(session, second) == "processed"  # not discarded
    copied = second.source_metadata["classification"]
    assert copied["reused_from"] == str(first.id) and copied["primary_category"] == "politics_governance"
    assert session.scalar(select(func.count()).select_from(ExtractionRun)) == 1


def test_an_unreadable_page_is_classified_from_the_excerpt_and_says_so(session, migrated_engine):
    item = add_item(session, title="Blocked publisher story", excerpt="Only this short feed excerpt is available.")
    blocked = ArticleFetchError("blocked host", transient=False)
    extractor = FakeNewsroomExtractor(classification(classification_confidence=0.4))
    summary = runner(migrated_engine, FakeFetch(default=blocked), extractor).run()
    session.expire_all()
    assert (summary.fetch_failed, summary.extracted) == (0, 1)
    assert item.source_metadata["classification"]["basis"] == "excerpt"
    assert "excerpt" in extractor.calls[0].note and extractor.calls[0].text == "Only this short feed excerpt is available."
    assert "blocked host" in item.source_metadata["fetch_error_note"]  # the reason is kept, nothing is invented


def test_an_item_with_nothing_to_read_is_set_aside_not_sent_to_the_model(session, migrated_engine):
    source = f.make_source(session)
    empty = f.make_source_item(session, source, title_redacted="", canonical_url=None, external_id="guid-empty")
    session.commit()
    extractor = FakeNewsroomExtractor()
    runner(migrated_engine, FakeFetch(), extractor).run()
    session.expire_all()
    assert status_of(session, empty) == "filtered" and "nothing to read" in empty.screen_reason
    assert extractor.calls == []


def test_failures_are_retryable_and_never_lose_the_article(session, migrated_engine):
    item = add_item(session, title="Budget presented", excerpt="x")
    failing = FakeNewsroomExtractor(retryable_error(), retryable_error(), retryable_error())
    r = runner(migrated_engine, FakeFetch(default=POLITICS), failing, max_attempts=3)
    first = r.run()
    assert (first.extraction_retry, first.extraction_failed) == (1, 0) and status_of(session, item) == "fetched"
    r.run()
    third = r.run()
    session.expire_all()
    assert third.extraction_failed == 1 and status_of(session, item) == "failed"
    assert item.title_redacted and item.article_text_redacted  # the original is intact
    assert session.scalar(select(func.count()).select_from(ExtractionRun).where(ExtractionRun.status == "failed")) == 3
    assert "classification" not in item.source_metadata


def test_a_requeued_article_gets_a_fresh_set_of_attempts(session, migrated_engine):
    """After an editor re-queues it, earlier failed runs no longer count against it."""
    from datetime import UTC, datetime

    item = add_item(session, title="Budget presented", excerpt="x")
    r = runner(migrated_engine, FakeFetch(default=POLITICS), FakeNewsroomExtractor(*[retryable_error()] * 3), max_attempts=3)
    for _ in range(3):
        r.run()
    session.expire_all()
    assert status_of(session, item) == "failed"
    item.processing_status = ProcessingStatus.FETCHED.value  # what POST /newsroom/articles/{id}/retry does
    item.source_metadata = {**item.source_metadata, "extraction_retry_epoch": datetime.now(UTC).isoformat()}
    session.commit()
    ok = FakeNewsroomExtractor(classification())
    summary = runner(migrated_engine, FakeFetch(default=POLITICS), ok, max_attempts=3).run()
    session.expire_all()
    assert summary.extracted == 1 and status_of(session, item) == "processed"


def test_without_a_classifier_articles_wait_instead_of_being_lost(session, migrated_engine):
    item = add_item(session, title="Budget presented", excerpt="x")
    summary = runner(migrated_engine, FakeFetch(default=POLITICS), None).run()
    session.expire_all()
    assert summary.extraction_skipped and status_of(session, item) == "fetched"


def test_a_social_post_is_kept_as_its_own_text(session, migrated_engine):
    source = f.make_source(session, kind="social")
    post = f.make_source_item(
        session, source, title_redacted="NUST fun run this Saturday", excerpt_redacted="Join us at the campus at 7am.",
        source_metadata={"content_kind": "social_post", "url": "https://fb.test/p/1"},
    )
    session.commit()
    fetch = FakeFetch()
    runner(migrated_engine, fetch, FakeNewsroomExtractor(classification(primary_category="education"))).run()
    session.expire_all()
    assert fetch.calls == [] and status_of(session, post) == "processed"


def test_the_newsroom_and_road_pipelines_use_different_locks():
    assert NEWSROOM_LOCK_KEY != LOCK_KEY


# ---- job wiring ------------------------------------------------------------------------------------------


def test_the_newsroom_job_skips_road_geocoding(monkeypatch):
    calls = []

    class FakeRunner:
        def run(self):
            return "summary"

    monkeypatch.setattr(pipeline_job, "get_settings", lambda: Settings(_env_file=None, app_mode="nust_newsroom"))
    monkeypatch.setattr(pipeline_job, "build_runner", lambda settings: FakeRunner())
    monkeypatch.setattr(pipeline_job, "run_location_step", lambda settings: calls.append("geocode"))
    assert pipeline_job.run_pipeline() == "summary" and calls == []

    monkeypatch.setattr(pipeline_job, "get_settings", lambda: Settings(_env_file=None))
    pipeline_job.run_pipeline()
    assert calls == ["geocode"]  # road-safety mode still geocodes


def test_the_newsroom_builds_the_newsroom_classifier(monkeypatch):
    from app.services.newsroom_extraction import NewsroomExtractor

    settings = Settings(_env_file=None, app_mode="nust_newsroom", openai_api_key="sk-test", newsroom_model="gpt-test")
    monkeypatch.setattr(pipeline_job, "get_engine", lambda: object())
    runner_ = pipeline_job.build_runner(settings)
    assert runner_._newsroom is True and isinstance(runner_._extractor, NewsroomExtractor)
    assert runner_._extractor.model_name == "gpt-test"
    default = pipeline_job.build_runner(Settings(_env_file=None, openai_api_key="sk-test"))
    assert default._newsroom is False and not isinstance(default._extractor, NewsroomExtractor)


def test_the_scheduler_never_runs_social_or_whatsapp_jobs_in_newsroom_mode(monkeypatch):
    from app.jobs import scheduler

    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(scheduler, "build_scheduler", fake_build)
    monkeypatch.setattr(scheduler, "run_scheduler", lambda s: 0)
    settings = Settings(
        _env_file=None, app_mode="nust_newsroom", social_ingestion_enabled=True, apify_api_token="x", whatsapp_enabled=True
    )
    scheduler.main(settings)
    assert captured["social_interval_seconds"] is None and captured["whatsapp_interval_seconds"] is None
    captured.clear()
    scheduler.main(Settings(_env_file=None, social_ingestion_enabled=True, apify_api_token="x", whatsapp_enabled=True))
    assert captured["social_interval_seconds"] is not None and captured["whatsapp_interval_seconds"] is not None
