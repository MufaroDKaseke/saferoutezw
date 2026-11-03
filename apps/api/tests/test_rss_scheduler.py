"""The standalone APScheduler process (``python -m app.jobs.scheduler``)."""

import logging
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import Settings
from app.jobs import scheduler as sched
from app.jobs.rss_poll import poll_rss_feeds

API_ROOT = Path(__file__).resolve().parents[1]


def noop() -> None:
    pass


@contextmanager
def running(scheduler: BlockingScheduler):
    """Run a (blocking) scheduler in a background thread for the duration of a test."""
    thread = threading.Thread(target=scheduler.start, daemon=True)
    thread.start()
    for _ in range(100):
        if scheduler.running:
            break
        threading.Event().wait(0.05)
    try:
        yield scheduler
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        thread.join(timeout=5)


# --- how the job is registered ---------------------------------------------------


def test_the_default_job_is_the_shared_rss_polling_cycle():
    scheduler = sched.build_scheduler(interval_seconds=180, poll_on_startup=False)

    assert scheduler.get_jobs()[0].func is poll_rss_feeds


def test_job_has_a_stable_id_and_runs_every_180_seconds_in_harare_time():
    scheduler = sched.build_scheduler(interval_seconds=180, poll_on_startup=False, job=noop)

    assert isinstance(scheduler, BlockingScheduler)
    assert str(scheduler.timezone) == "Africa/Harare"
    (job,) = scheduler.get_jobs()
    assert job.id == "rss_polling" == sched.JOB_ID
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval == timedelta(seconds=180)
    assert str(job.trigger.timezone) == "Africa/Harare"


def test_job_never_overlaps_itself_and_coalesces_missed_runs():
    scheduler = sched.build_scheduler(interval_seconds=180, poll_on_startup=False, job=noop)

    (job,) = scheduler.get_jobs()
    assert job.max_instances == 1
    assert job.coalesce is True
    # A laptop that slept through a tick still polls once when it wakes, but a
    # tick missed by more than a full interval is dropped rather than replayed.
    assert job.misfire_grace_time == 180


def test_interval_comes_from_the_configured_value():
    scheduler = sched.build_scheduler(interval_seconds=600, poll_on_startup=False, job=noop)

    (job,) = scheduler.get_jobs()
    assert job.trigger.interval == timedelta(seconds=600)
    assert job.misfire_grace_time == 600


def test_registering_twice_replaces_the_job_instead_of_duplicating_it():
    scheduler = sched.build_scheduler(interval_seconds=60, poll_on_startup=False, job=noop)
    sched.register_polling_job(scheduler, interval_seconds=90, poll_on_startup=False, job=noop)

    with running(scheduler):
        jobs = scheduler.get_jobs()
        assert [j.id for j in jobs] == ["rss_polling"]
        assert jobs[0].trigger.interval == timedelta(seconds=90)


# --- running behaviour ------------------------------------------------------------------


def test_first_cycle_runs_immediately_when_poll_on_startup_is_true():
    first_run = threading.Event()
    scheduler = sched.build_scheduler(interval_seconds=60, poll_on_startup=True, job=first_run.set)

    with running(scheduler):
        assert first_run.wait(timeout=5), "no cycle ran at startup"


def test_first_cycle_waits_a_full_interval_when_poll_on_startup_is_false():
    ran = threading.Event()
    scheduler = sched.build_scheduler(interval_seconds=60, poll_on_startup=False, job=ran.set)

    with running(scheduler):
        assert not ran.wait(timeout=1.0), "a cycle ran although poll_on_startup is false"
        assert scheduler.get_job("rss_polling").next_run_time is not None


def test_cycles_repeat_on_the_interval():
    runs = []
    two_runs = threading.Event()

    def job():
        runs.append(1)
        if len(runs) >= 2:
            two_runs.set()

    scheduler = sched.build_scheduler(interval_seconds=1, poll_on_startup=True, job=job)

    with running(scheduler):
        assert two_runs.wait(timeout=6), "the job did not repeat"


def test_a_failing_cycle_is_logged_and_the_scheduler_keeps_running(caplog):
    attempts = []
    retried = threading.Event()

    def failing_job():
        attempts.append(1)
        if len(attempts) >= 2:
            retried.set()
        raise RuntimeError("postgres is down")

    scheduler = sched.build_scheduler(interval_seconds=1, poll_on_startup=True, job=failing_job)

    with caplog.at_level(logging.INFO):
        with running(scheduler):
            assert retried.wait(timeout=6), "the scheduler stopped after the first failure"
            assert scheduler.running
    assert "raised an exception" in caplog.text and "postgres is down" in caplog.text


# --- graceful shutdown -----------------------------------------------------------------


class StubScheduler:
    def __init__(self, interrupt: BaseException | None):
        self.interrupt, self.shutdowns = interrupt, []

    def start(self):
        if self.interrupt:
            raise self.interrupt

    def shutdown(self, wait=True):
        self.shutdowns.append(wait)


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt(), SystemExit(0)])
def test_ctrl_c_shuts_the_scheduler_down_cleanly_and_exits_zero(interrupt, caplog):
    stub = StubScheduler(interrupt)

    with caplog.at_level(logging.INFO):
        code = sched.run_scheduler(stub)

    assert code == 0
    assert stub.shutdowns == [True]  # waits for an in-flight cycle to finish
    assert "stopped" in caplog.text


def test_a_normal_return_from_start_does_not_trigger_a_second_shutdown():
    stub = StubScheduler(None)

    assert sched.run_scheduler(stub) == 0
    assert stub.shutdowns == []


# --- the command line entry point ---------------------------------------------------------


def test_main_builds_the_scheduler_from_settings_and_runs_it(monkeypatch):
    seen = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        return "scheduler"

    monkeypatch.setattr(sched, "build_scheduler", fake_build)
    monkeypatch.setattr(sched, "run_scheduler", lambda s: seen.setdefault("ran", s) and 0)

    code = sched.main(Settings(_env_file=None, rss_poll_interval_seconds=240, rss_poll_on_startup=False))

    assert code == 0
    assert seen["interval_seconds"] == 240 and seen["poll_on_startup"] is False and seen["ran"] == "scheduler"


def test_main_does_nothing_when_the_scheduler_is_disabled(monkeypatch, caplog):
    def must_not_build(**kwargs):
        raise AssertionError("scheduler must not be built when disabled")

    monkeypatch.setattr(sched, "build_scheduler", must_not_build)

    with caplog.at_level(logging.INFO):
        code = sched.main(Settings(_env_file=None, rss_scheduler_enabled=False))

    assert code == 0
    assert "RSS_SCHEDULER_ENABLED" in caplog.text


def run_python(*args: str, **env) -> subprocess.CompletedProcess:
    import os

    return subprocess.run(
        [sys.executable, "-I", *args] if args and args[0] == "-c" else [sys.executable, *args],
        cwd=API_ROOT, capture_output=True, text=True, timeout=60, env={**os.environ, **env},
    )


def test_python_dash_m_entry_point_exits_cleanly_when_disabled():
    result = run_python("-m", "app.jobs.scheduler", RSS_SCHEDULER_ENABLED="false")

    assert result.returncode == 0, result.stderr
    assert "RSS_SCHEDULER_ENABLED" in result.stderr + result.stdout


def test_importing_the_api_application_never_starts_or_even_loads_the_scheduler():
    result = run_python(
        "-c",
        "import sys, threading; import app.main; "
        "print('apscheduler' in sys.modules, [t.name for t in threading.enumerate()])",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("False"), result.stdout
