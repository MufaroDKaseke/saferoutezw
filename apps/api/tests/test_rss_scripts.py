"""Seeding the configured feeds, and the one-off ``run_rss_once.py`` command."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

import db_factories as f
from app.ingestion.feeds import RSS_FEEDS
from app.ingestion.sources import seed_rss_sources
from app.models import IngestionRun, Source, SourceItem
from feed_server import rss_document

pytestmark = pytest.mark.usefixtures("migrated_engine")

API_ROOT = Path(__file__).resolve().parents[1]


def run_script(name: str, settings, timeout: int = 120, **env) -> subprocess.CompletedProcess:
    """Run apps/api/scripts/<name> exactly as a developer would, against the test database."""
    environment = {**os.environ, "POSTGRES_DB": settings.postgres_test_db, **env}
    return subprocess.run(
        [sys.executable, str(API_ROOT / "scripts" / name)],
        cwd=API_ROOT, capture_output=True, text=True, timeout=timeout, env=environment,
    )


# --- seeding -----------------------------------------------------------------------------


def test_seed_adds_one_enabled_rss_source_per_configured_feed(session):
    added = seed_rss_sources(session)
    session.commit()

    assert added == len(RSS_FEEDS)
    sources = session.scalars(select(Source)).all()
    assert {s.name: s.feed_url for s in sources} == RSS_FEEDS
    assert all(s.kind == "rss" and s.enabled for s in sources)
    assert {s.verification_tier for s in sources} == {"unverified"}  # editors raise this deliberately


def test_seeding_twice_adds_nothing_the_second_time(session):
    seed_rss_sources(session)
    session.commit()

    assert seed_rss_sources(session) == 0
    assert session.scalar(select(func.count()).select_from(Source)) == len(RSS_FEEDS)


def test_seeding_never_undoes_a_developers_changes(session):
    seed_rss_sources(session)
    session.commit()
    herald = session.scalars(select(Source).where(Source.name == "The Herald")).one()
    herald.enabled = False
    herald.poll_interval_seconds = 3600
    session.commit()

    seed_rss_sources(session)
    session.commit()

    session.refresh(herald)
    assert herald.enabled is False and herald.poll_interval_seconds == 3600


def test_seed_script_populates_the_database(session, settings):
    result = run_script("seed_rss_sources.py", settings)

    assert result.returncode == 0, result.stderr
    assert f"Added {len(RSS_FEEDS)} new RSS source(s)" in result.stdout
    assert run_script("seed_rss_sources.py", settings).stdout.count("Added 0 new RSS source(s)") == 1


# --- run_rss_once.py -----------------------------------------------------------------------


def test_run_rss_once_polls_every_enabled_source_and_exits_zero(session, settings, feed_server):
    url = feed_server.serve("/feed", rss_document([
        {"title": "Story one", "guid": "g1", "link": "https://news.example.test/one/"},
        {"title": "Story two", "guid": "g2", "link": "https://news.example.test/two/"},
    ]))
    source = f.make_source(session)
    source.feed_url = url
    session.commit()

    result = run_script("run_rss_once.py", settings)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"{source.name}: fetched=2 new=2 duplicates=0" in result.stdout
    assert "RSS poll cycle finished: sources=1 succeeded=1 failed=0" in result.stdout
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 2
    assert session.scalar(select(func.count()).select_from(IngestionRun)) == 1


def test_run_rss_once_twice_reports_the_second_poll_as_all_duplicates(session, settings, feed_server):
    url = feed_server.serve("/feed", rss_document([
        {"title": "Story one", "guid": "g1", "link": "https://news.example.test/one/"},
    ]))
    f.make_source(session).feed_url = url
    session.commit()

    run_script("run_rss_once.py", settings)
    second = run_script("run_rss_once.py", settings)

    assert "fetched=1 new=0 duplicates=1" in second.stdout
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 1


def test_run_rss_once_survives_a_dead_feed_and_still_exits_zero(session, settings, feed_server):
    good_url = feed_server.serve("/good", rss_document([
        {"title": "Story", "guid": "g1", "link": "https://news.example.test/s/"},
    ]))
    dead_url = feed_server.serve("/dead", b"gone", status=404)
    for url in (good_url, dead_url):
        f.make_source(session).feed_url = url
    session.commit()

    result = run_script("run_rss_once.py", settings)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "succeeded=1 failed=1" in result.stdout
    assert sorted(session.scalars(select(IngestionRun.status))) == ["failed", "succeeded"]


def test_run_rss_once_exits_nonzero_instead_of_hanging_when_postgres_is_down(settings):
    # Nothing listens on port 1. Without a connect timeout psycopg waits forever on Windows.
    result = run_script("run_rss_once.py", settings, timeout=45, POSTGRES_PORT="1", POSTGRES_CONNECT_TIMEOUT="1")

    assert result.returncode == 1
    assert "RSS poll cycle failed" in result.stdout
