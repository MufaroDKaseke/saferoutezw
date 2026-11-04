"""Poll allow-listed social accounts and store their posts as ``source_items``.

One account per Actor run, one tracked ``ingestion_run`` per poll. The flow mirrors
``app.ingestion.rss`` (advisory lock, no transaction open during the slow call, database-level
de-duplication) and ends in the same place: pending ``source_items`` that the shared article
pipeline screens, redacts and sends to OpenAI. Nothing here knows about OpenAI or incidents.

Allowlist guarantees
--------------------
* Only accounts with a ``social_sources`` row whose ``sources.enabled`` is true are polled,
  and only through an adapter that exists for their platform.
* Every returned item is judged by the platform adapter: confirmed origin is accepted,
  another account's content is rejected (counted, not stored), and anything whose origin
  cannot be confirmed goes to ``social_quarantine`` and is never processed.
* Cost is bounded per run (timeout, spend ceiling, row cap, newest-since window) and per day
  (``max_runs_per_day``).
"""

from __future__ import annotations

import hashlib
import logging
import math
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.normalized import report_row
from app.ingestion.rss import (
    SKIPPED,
    SourceOutcome,
    _insert_items,
    _unique_rows,
    safe_error_message,
    source_advisory_lock,
)
from app.ingestion.social.base import (
    ACCEPT,
    QUARANTINE,
    REJECT,
    Notice,
    PlatformAdapter,
    SocialSourceRef,
)
from app.ingestion.social.registry import get_adapter
from app.ingestion.social.runner import ActorRunner
from app.models import IngestionRun, SocialQuarantine, SocialSource, Source
from app.models.enums import CollectionStatus, IngestionStatus, SourceKind

log = logging.getLogger(__name__)

WINDOW_MARGIN_HOURS = 6  # overlap so a late-running poll never leaves a gap; the database drops repeats
MAX_WINDOW_HOURS = 24 * 14


@dataclass(frozen=True)
class SocialOutcome(SourceOutcome):
    quarantined: int = 0
    rejected: int = 0


def social_lock_key(source_id: uuid.UUID) -> int:
    digest = hashlib.blake2b(f"saferoutezw:social_source:{source_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def is_due(source: SocialSourceRef, now: datetime, retry_after_error: timedelta) -> bool:
    if source.last_polled_at is None:
        return True
    wait = timedelta(seconds=source.poll_interval_seconds)
    if source.collection_status == CollectionStatus.ERROR.value:
        wait = min(wait, retry_after_error)
    return now >= source.last_polled_at + wait


def since_hours(source: SocialSourceRef, now: datetime, first_run_hours: int) -> int:
    """How far back to ask for posts: since the last success (plus margin), bounded."""
    if source.last_success_at is None:
        return first_run_hours
    elapsed = (now - source.last_success_at).total_seconds() / 3600
    return max(1, min(MAX_WINDOW_HOURS, math.ceil(elapsed) + WINDOW_MARGIN_HOURS))


def _summary(counter: Counter[str]) -> str:
    return ", ".join(f"{reason} x{n}" for reason, n in counter.most_common())


class SocialIngestor:
    def __init__(
        self,
        engine: Engine,
        runner: ActorRunner,
        *,
        post_max_chars: int = 8000,
        run_timeout_seconds: int = 600,
        max_charge_usd: float = 0.25,
        max_runs_per_day: int = 24,
        first_run_lookback_hours: int = 48,
        retry_after_error: timedelta = timedelta(minutes=30),
    ) -> None:
        self._engine = engine
        self._runner = runner
        self._max_chars = post_max_chars
        self._timeout = run_timeout_seconds
        self._max_charge = max_charge_usd
        self._max_runs_per_day = max_runs_per_day
        self._first_run_hours = first_run_lookback_hours
        self._retry_after_error = retry_after_error
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    # -- discovery -------------------------------------------------------------------
    def due_sources(self, now: datetime | None = None) -> list[SocialSourceRef]:
        """Enabled, supported accounts whose interval has elapsed (read in one short transaction)."""
        now = now or datetime.now(UTC)
        with self._sessions() as db:
            refs = self._query(db)
        return [r for r in refs if r.enabled and get_adapter(r.platform) and is_due(r, now, self._retry_after_error)]

    @staticmethod
    def _query(db: Session, source_id: uuid.UUID | None = None) -> list[SocialSourceRef]:
        query = (
            select(Source, SocialSource)
            .join(SocialSource, SocialSource.source_id == Source.id)
            .where(Source.kind == SourceKind.SOCIAL.value)
            .order_by(Source.name)
        )
        if source_id is not None:
            query = query.where(Source.id == source_id)
        return [
            SocialSourceRef(
                source_id=s.id, name=s.name, platform=c.platform, account_url=c.account_url,
                platform_account_id=c.platform_account_id, actor_id=c.actor_id, enabled=s.enabled,
                poll_interval_seconds=s.poll_interval_seconds, max_posts_per_run=c.max_posts_per_run,
                last_polled_at=c.last_polled_at, last_success_at=c.last_success_at,
                last_post_id=c.last_post_id, last_post_at=c.last_post_at, collection_status=c.collection_status,
            )
            for s, c in db.execute(query)
        ]

    # -- one account -----------------------------------------------------------------
    def ingest(self, source_id: uuid.UUID, *, force: bool = False, lookback_hours: int | None = None) -> SocialOutcome:
        with source_advisory_lock(self._engine, social_lock_key(source_id), str(source_id)) as acquired:
            if not acquired:
                return SocialOutcome(str(source_id), SKIPPED, error="another worker is polling it")
            with self._sessions() as db:  # re-read under the lock: an admin may have just changed it
                found = self._query(db, source_id)
            if not found:
                return SocialOutcome(str(source_id), SKIPPED, error="not an allow-listed social source")
            source = found[0]
            now = datetime.now(UTC)
            adapter = get_adapter(source.platform)
            if adapter is None:
                log.info("%s: platform %s has no adapter; not polled", source.name, source.platform)
                return SocialOutcome(source.name, SKIPPED, error=f"platform {source.platform} is not supported yet")
            if not source.enabled:
                return SocialOutcome(source.name, SKIPPED, error="source is disabled")
            if not force and not is_due(source, now, self._retry_after_error):
                return SocialOutcome(source.name, SKIPPED, error="not due yet")
            if self._runs_in_last_day(now) >= self._max_runs_per_day:
                log.warning("%s: daily Actor run budget (%d) reached; not polled", source.name, self._max_runs_per_day)
                return SocialOutcome(source.name, SKIPPED, error="daily run budget reached")

            run_id = self._start_run(source, now)
            try:
                rows = self._runner.run(
                    source.actor_id,
                    adapter.build_input(source, since_hours=lookback_hours or since_hours(source, now, self._first_run_hours)),
                    max_items=adapter.max_items(source),
                    timeout_seconds=self._timeout,
                    max_charge_usd=self._max_charge,
                )
                return self._process(source, adapter, run_id, rows)
            except Exception as exc:  # noqa: BLE001 - one bad account must not stop the others
                return self._fail(source, run_id, exc)
            except BaseException:  # Ctrl+C: do not leave the run "running"
                self._fail(source, run_id, "interrupted before completion")
                raise

    # -- processing ------------------------------------------------------------------
    def _process(
        self, source: SocialSourceRef, adapter: PlatformAdapter, run_id: uuid.UUID, rows: list[dict]
    ) -> SocialOutcome:
        notices: list[Notice] = []
        posts: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            notice = adapter.notice(row)
            if notice is not None:
                notices.append(notice)
            else:
                posts.append(row)
        posts = posts[: source.max_posts_per_run]  # the Actor's cap is a request; ours is the rule

        accepted, quarantine_rows = [], []
        rejected: Counter[str] = Counter()
        quarantined: Counter[str] = Counter()
        learned_ids: set[str] = set()
        for post in posts:
            verdict = adapter.judge(post, source, max_chars=self._max_chars)
            if verdict.action == ACCEPT and verdict.report is not None:
                accepted.append(verdict.report)
                if verdict.learned_account_id:
                    learned_ids.add(verdict.learned_account_id)
            elif verdict.action == REJECT:
                rejected[verdict.reason or "rejected"] += 1
            elif verdict.action == QUARANTINE:
                quarantined[verdict.reason or "unverified"] += 1
                quarantine_rows.append(
                    {
                        "source_id": source.source_id, "ingestion_run_id": run_id,
                        "reason": verdict.reason or "unverified", "external_id": verdict.external_id,
                        "post_url": verdict.post_url, "summary": verdict.detail,
                    }
                )

        item_rows = _unique_rows([report_row(r, source.source_id, run_id) for r in accepted])
        newest = max(accepted, key=lambda r: r.published_at or datetime.min.replace(tzinfo=UTC), default=None)
        blocking = next((n for n in notices if n.blocking), None) if not posts else None

        problems = []
        if quarantined:
            problems.append(f"quarantined: {_summary(quarantined)}")
        if rejected:
            problems.append(f"rejected: {_summary(rejected)}")
        problem_text = "; ".join(problems) or None

        with self._sessions.begin() as db:
            still_enabled = bool(db.scalar(select(Source.enabled).where(Source.id == source.source_id)))
            inserted = _insert_items(db, item_rows) if still_enabled else 0
            if quarantine_rows:
                db.add_all(SocialQuarantine(**r) for r in quarantine_rows)
            state: dict = {
                "collection_status": CollectionStatus.BLOCKED.value if blocking else CollectionStatus.OK.value,
                "last_error": safe_error_message(f"{blocking.reason}: {blocking.message}") if blocking else problem_text,
            }
            if not blocking:
                state["last_success_at"] = func.now()
            if len(learned_ids) == 1 and not source.platform_account_id:
                state["platform_account_id"] = next(iter(learned_ids))
            if newest is not None and (
                source.last_post_at is None or (newest.published_at and newest.published_at > source.last_post_at)
            ):
                state["last_post_id"] = newest.external_id
                state["last_post_at"] = newest.published_at
            db.execute(update(SocialSource).where(SocialSource.source_id == source.source_id).values(**state))

        fetched = len(posts)
        duplicates = len(item_rows) - inserted if still_enabled else 0
        issues = sum(quarantined.values()) + sum(rejected.values())
        if blocking:
            status = IngestionStatus.FAILED
            message = safe_error_message(f"{blocking.reason}: {blocking.message}")
        else:
            status = IngestionStatus.PARTIAL if issues else IngestionStatus.SUCCEEDED
            message = problem_text
        self._finish(run_id, status, fetched, inserted, duplicates, issues if not blocking else 1, message)
        log.info(
            "%s: fetched=%d new=%d duplicates=%d quarantined=%d rejected=%d",
            source.name, fetched, inserted, duplicates, sum(quarantined.values()), sum(rejected.values()),
        )
        return SocialOutcome(
            source.name, status.value, fetched, inserted, duplicates, message, run_id,
            quarantined=sum(quarantined.values()), rejected=sum(rejected.values()),
        )

    # -- short transactions ------------------------------------------------------------
    def _runs_in_last_day(self, now: datetime) -> int:
        with self._sessions() as db:
            return int(
                db.scalar(
                    select(func.count())
                    .select_from(IngestionRun)
                    .join(Source, Source.id == IngestionRun.source_id)
                    .where(Source.kind == SourceKind.SOCIAL.value, IngestionRun.started_at >= now - timedelta(days=1))
                )
                or 0
            )

    def _start_run(self, source: SocialSourceRef, now: datetime) -> uuid.UUID:
        with self._sessions.begin() as db:
            run = IngestionRun(source_id=source.source_id, status=IngestionStatus.RUNNING.value)
            db.add(run)
            db.flush()
            # Counted as a poll the moment the (billable) Actor starts, so a crash cannot cause a rapid retry loop.
            db.execute(update(SocialSource).where(SocialSource.source_id == source.source_id).values(last_polled_at=now))
            return run.id

    def _finish(
        self, run_id: uuid.UUID, status: IngestionStatus, fetched: int, inserted: int,
        duplicates: int, errors: int, message: str | None,
    ) -> None:
        with self._sessions.begin() as db:
            db.execute(
                update(IngestionRun)
                .where(IngestionRun.id == run_id)
                .values(
                    status=status.value, completed_at=func.now(), fetched_count=fetched,
                    inserted_count=inserted, duplicate_count=duplicates, error_count=errors,
                    error_message=message,
                )
            )

    def _fail(self, source: SocialSourceRef, run_id: uuid.UUID, error: BaseException | str) -> SocialOutcome:
        message = safe_error_message(error)
        self._finish(run_id, IngestionStatus.FAILED, 0, 0, 0, 1, message)
        with self._sessions.begin() as db:
            db.execute(
                update(SocialSource)
                .where(SocialSource.source_id == source.source_id)
                .values(collection_status=CollectionStatus.ERROR.value, last_error=message)
            )
        log.warning("%s: social poll failed (will retry): %s", source.name, message)
        return SocialOutcome(source.name, IngestionStatus.FAILED.value, error=message, run_id=run_id)
