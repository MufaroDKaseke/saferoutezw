"""Schema, settings, scheduler and script wiring for the article pipeline."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import inspect, select, text

import db_factories as f
from app.core.config import Settings
from app.jobs import pipeline_job
from app.jobs import scheduler as sched
from app.jobs.pipeline_job import run_pipeline
from app.models import ExtractionRun, SourceItem
from app.models.enums import ProcessingStatus
from conftest import alembic_config

pytestmark = pytest.mark.usefixtures("migrated_engine")

API_ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "7ba24614c7eb"
NEW_COLUMNS = {"article_text_redacted", "fetch_status", "fetch_error", "fetched_at", "content_hash", "screen_reason"}


# --- migration -------------------------------------------------------------------------------


def test_source_items_and_extraction_runs_have_the_new_columns(migrated_engine):
    inspector = inspect(migrated_engine)
    assert NEW_COLUMNS <= {c["name"] for c in inspector.get_columns("source_items")}
    assert {"prompt_version", "input_tokens", "output_tokens", "completed_at"} <= {
        c["name"] for c in inspector.get_columns("extraction_runs")
    }
    assert "ix_source_items_content_hash" in {i["name"] for i in inspector.get_indexes("source_items")}


@pytest.mark.parametrize("state", [s.value for s in ProcessingStatus])
def test_every_processing_status_is_accepted_by_the_database(session, state):
    item = f.make_source_item(session, f.make_source(session), processing_status=state)
    assert item.processing_status == state


def test_unknown_statuses_and_fetch_statuses_are_still_rejected(session, db_error):
    source = f.make_source(session)
    with db_error(session, "23514"):
        f.make_source_item(session, source, processing_status="bogus")
    with db_error(session, "23514"):
        f.make_source_item(session, source, fetch_status="maybe")


def test_new_columns_are_optional_so_existing_rows_stay_valid(session):
    item = f.make_source_item(session, f.make_source(session))
    assert item.processing_status == "pending"
    assert item.article_text_redacted is None and item.content_hash is None and item.fetch_status is None


def test_downgrade_and_upgrade_keep_existing_rows(session, migrated_engine, test_database_url):
    source = f.make_source(session)
    states = ["filtered", "screened", "fetched", "fetch_failed", "processed"]
    ids = {s: f.make_source_item(session, source, processing_status=s).id for s in states}
    session.commit()
    cfg = alembic_config(test_database_url)
    try:
        command.downgrade(cfg, PREVIOUS_REVISION)
        with migrated_engine.connect() as conn:
            rows = dict(conn.execute(text("SELECT id, processing_status FROM source_items")).all())
            assert not (NEW_COLUMNS & {c["name"] for c in inspect(conn).get_columns("source_items")})
        assert {s: rows[i] for s, i in ids.items()} == {
            "filtered": "discarded", "screened": "pending", "fetched": "pending",
            "fetch_failed": "failed", "processed": "processed",
        }
    finally:
        command.upgrade(cfg, "head")
    session.expire_all()
    assert session.scalar(select(SourceItem.processing_status).where(SourceItem.id == ids["processed"])) == "processed"


def test_the_human_approval_safeguard_is_untouched(session):
    incident = f.make_incident(session)
    session.commit()
    with pytest.raises(Exception, match="approv|review"):
        incident.status = "approved"  # no editorial review exists, so the database refuses
        session.flush()
    session.rollback()


def test_extraction_runs_have_the_new_fields(session):
    item = f.make_source_item(session, f.make_source(session))
    run = ExtractionRun(source_item_id=item.id, model_name="m", prompt_version="v1", input_tokens=5, output_tokens=2)
    session.add(run)
    session.flush()
    assert (run.prompt_version, run.input_tokens, run.output_tokens, run.completed_at) == ("v1", 5, 2, None)


# --- settings --------------------------------------------------------------------------------


def test_pipeline_settings_have_safe_defaults():
    s = Settings(_env_file=None)
    assert (s.openai_model, s.pipeline_enabled, s.pipeline_interval_seconds) == ("gpt-4o-mini", True, 180)
    assert s.openai_api_key is None and s.extraction_min_confidence == 0.6
    assert s.pipeline_max_attempts == 3 and s.article_fetch_delay_seconds >= 0


def test_pipeline_settings_are_validated():
    for bad in ({"pipeline_interval_seconds": 5}, {"extraction_min_confidence": 2}, {"pipeline_batch_size": 0}):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **bad)


# --- job wiring ------------------------------------------------------------------------------


def test_the_scheduler_has_only_the_rss_job_unless_the_pipeline_is_requested():
    scheduler = sched.build_scheduler(interval_seconds=180, poll_on_startup=False)
    assert [j.id for j in scheduler.get_jobs()] == [sched.JOB_ID]


def test_the_pipeline_job_runs_beside_polling_without_overlapping_itself():
    scheduler = sched.build_scheduler(interval_seconds=180, poll_on_startup=False, pipeline_interval_seconds=240)
    jobs = {j.id: j for j in scheduler.get_jobs()}
    assert set(jobs) == {sched.JOB_ID, sched.PIPELINE_JOB_ID}
    job = jobs[sched.PIPELINE_JOB_ID]
    assert job.func is run_pipeline and job.max_instances == 1 and job.coalesce is True
    assert job.trigger.interval.total_seconds() == 240


def test_main_registers_the_pipeline_job_from_settings(monkeypatch):
    captured = {}

    def fake_build(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(sched, "build_scheduler", fake_build)
    monkeypatch.setattr(sched, "run_scheduler", lambda scheduler: 0)
    sched.main(Settings(_env_file=None, pipeline_interval_seconds=300))
    assert captured["pipeline_interval_seconds"] == 300
    sched.main(Settings(_env_file=None, pipeline_enabled=False))
    assert captured["pipeline_interval_seconds"] is None


def test_the_pipeline_job_does_nothing_when_disabled(monkeypatch):
    monkeypatch.setattr(pipeline_job, "get_settings", lambda: Settings(_env_file=None, pipeline_enabled=False))
    assert run_pipeline() is None


def test_the_runner_has_no_extractor_without_a_key_and_one_with_it(monkeypatch):
    monkeypatch.setattr(pipeline_job, "get_engine", lambda: object())
    assert pipeline_job.build_runner(Settings(_env_file=None))._extractor is None
    runner = pipeline_job.build_runner(Settings(_env_file=None, openai_api_key="sk-test"))
    assert runner._extractor.model_name == "gpt-4o-mini"


def test_a_failing_cycle_is_logged_and_raised(monkeypatch, caplog):
    def boom(settings=None):
        raise RuntimeError("PostgreSQL is down")

    monkeypatch.setattr(pipeline_job, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(pipeline_job, "build_runner", boom)
    with pytest.raises(RuntimeError), caplog.at_level("ERROR"):
        run_pipeline()
    assert "Article pipeline cycle failed" in caplog.text


# --- run_pipeline_once.py --------------------------------------------------------------------


def run_script(settings, timeout=120, **env) -> subprocess.CompletedProcess:
    environment = {**os.environ, "POSTGRES_DB": settings.postgres_test_db, "OPENAI_API_KEY": "", **env}
    return subprocess.run(
        [sys.executable, str(API_ROOT / "scripts" / "run_pipeline_once.py")],
        cwd=API_ROOT, capture_output=True, text=True, timeout=timeout, env=environment,
    )


def test_run_pipeline_once_screens_even_without_an_openai_key(session, settings):
    source = f.make_source(session)
    item = f.make_source_item(session, source, title_redacted="Weather outlook", excerpt_redacted="Sunny.")
    session.commit()

    result = run_script(settings)

    assert result.returncode == 0, result.stderr
    assert "Article pipeline:" in result.stderr + result.stdout
    session.refresh(item)
    assert item.processing_status == "filtered"


def test_run_pipeline_once_exits_one_when_the_database_is_unreachable(settings):
    result = run_script(settings, POSTGRES_PORT="1", POSTGRES_CONNECT_TIMEOUT="1")
    assert result.returncode == 1


def test_run_pipeline_once_exits_zero_when_disabled(settings):
    assert run_script(settings, PIPELINE_ENABLED="false").returncode == 0


def test_the_api_never_imports_the_pipeline_or_openai():
    code = "import app.main, sys; assert 'openai' not in sys.modules and 'app.services.pipeline' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], cwd=API_ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
