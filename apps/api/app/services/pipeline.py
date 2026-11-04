"""The article pipeline: screen -> fetch full article -> redact -> OpenAI -> candidate incident.

It continues where ``app.ingestion.rss`` stops: RSS ingestion stores ``pending``
source items; this module moves them through ``source_items.processing_status``::

    pending --screen--> filtered                       (not road related; never fetched)
                    \\-> screened --fetch--> fetch_failed   (never sent to the AI)
                                       \\-> fetched --extract--> processed  (candidate incident)
                                                            \\-> discarded  (not an incident / duplicate)
                                                            \\-> failed     (attempts exhausted)

Guarantees
----------
* **Full article only.** The AI receives ``article_text_redacted`` of an item whose
  page was fetched. If the page cannot be read the item becomes ``fetch_failed``; there
  is no silent fallback to the headline or RSS excerpt.
* **Redaction before storage and before the AI.** Titles and excerpts are redacted when
  screened; the article is redacted before it is written to the database.
* **Humans decide.** Incidents are only ever inserted as ``candidate``. Nothing here
  can approve or publish one (database triggers also forbid it without a human review).
* **No transaction is open during HTTP or OpenAI calls**, and each result is written
  with a compare-and-swap on ``processing_status`` so a second process cannot double-write.
* **Idempotent and restartable.** A crash leaves an item in its previous state; the next
  cycle retries it. Fetch and extraction attempts are bounded (``max_attempts``).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ingestion.article import ArticleFetchError, ArticleFetchFn
from app.ingestion.rss import safe_error_message
from app.models import AuditEvent, ExtractionRun, Incident, IncidentEvidence, Source, SourceItem
from app.models.enums import (
    EvidenceRole,
    ExtractionStatus,
    FetchStatus,
    IncidentStatus,
    ProcessingStatus,
    ReviewPriority,
    Severity,
    VerificationTier,
)
from app.schemas.extraction import ExtractionResult
from app.services.extraction import (
    ExtractionError,
    ExtractionInput,
    ExtractionOutput,
    Extractor,
    ExtractorUnavailable,
)
from app.services.intelligence import store_intelligence
from app.services.redaction import redact
from app.taxonomy import PrimaryCategory
from app.services.screening import screen

log = logging.getLogger(__name__)

SCREEN_BATCH = 500  # screening is local and cheap, so it takes bigger bites than fetch/extract
TIER_WEIGHT = {
    VerificationTier.OFFICIAL.value: 1.0,
    VerificationTier.ESTABLISHED_MEDIA.value: 0.9,
    VerificationTier.COMMUNITY.value: 0.6,
    VerificationTier.UNVERIFIED.value: 0.5,
}
SEVERITY_PRIORITY = {
    Severity.FATAL.value: ReviewPriority.HIGH.value,
    Severity.SERIOUS.value: ReviewPriority.NORMAL.value,
    Severity.UNKNOWN.value: ReviewPriority.NORMAL.value,
    Severity.MINOR.value: ReviewPriority.LOW.value,
}
CORROBORATION_BONUS = 0.05
CORROBORATION_CAP = 0.95
DUPLICATE_WINDOW = timedelta(days=1)
LOCK_KEY = int.from_bytes(
    hashlib.blake2b(b"saferoutezw:article_pipeline", digest_size=8).digest(), "big", signed=True
)


@dataclass
class PipelineSummary:
    """Counts for one run of all three stages."""

    screened: int = 0  # possibly relevant, queued for fetching
    filtered: int = 0  # not road related
    fetched: int = 0
    fetch_failed: int = 0
    fetch_retry: int = 0  # transient failure, will try again next cycle
    extracted: int = 0  # extraction calls that returned a valid result
    incidents_created: int = 0
    intelligence_records: int = 0  # classified records stored (incident-linked or not)
    corroborated: int = 0  # attached to an existing incident
    discarded: int = 0
    extraction_failed: int = 0
    extraction_retry: int = 0
    skipped_locked: bool = False  # another pipeline process holds the lock
    extraction_skipped: str | None = None  # why extraction did not run (e.g. no API key)
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def parse_categories(value: str | None) -> frozenset[str] | None:
    """'a,b' -> {'a','b'}; empty means every category. Unknown names are an error, not ignored."""
    names = {n.strip() for n in (value or "").split(",") if n.strip()}
    unknown = names - {c.value for c in PrimaryCategory}
    if unknown:
        raise ValueError(f"unknown intelligence categories: {', '.join(sorted(unknown))}")
    return frozenset(names) or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_social_post(item: SourceItem) -> bool:
    return (item.source_metadata or {}).get("content_kind") == "social_post"


def _credibility(confidence: float, tier: str) -> float:
    return round(max(0.0, min(1.0, confidence * TIER_WEIGHT.get(tier, 0.5))), 2)


def _new_reference_code(when: datetime) -> str:
    return f"SRZ-{when:%Y%m%d}-{secrets.token_hex(3).upper()}"


class PipelineRunner:
    def __init__(
        self,
        engine: Engine,
        *,
        fetch_article: ArticleFetchFn,
        extractor: Extractor | None,
        batch_size: int = 25,
        max_attempts: int = 3,
        min_confidence: float = 0.6,
        enabled_categories: frozenset[str] | None = None,
    ) -> None:
        self._engine = engine
        self._fetch_article = fetch_article
        self._extractor = extractor
        self._batch = batch_size
        self._max_attempts = max_attempts
        self._min_confidence = min_confidence
        self._enabled_categories = enabled_categories
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    # ------------------------------------------------------------------ run
    def run(self) -> PipelineSummary:
        summary = PipelineSummary()
        started = datetime.now()
        with self._lock() as acquired:
            if not acquired:
                summary.skipped_locked = True
                log.info("Article pipeline skipped: another process is already running it")
                return summary
            self.screen_pending(summary)
            self.fetch_screened(summary)
            self.extract_fetched(summary)
        summary.seconds = (datetime.now() - started).total_seconds()
        log.info(
            "Article pipeline: screened=%d filtered=%d fetched=%d fetch_failed=%d fetch_retry=%d "
            "extracted=%d incidents=%d corroborated=%d discarded=%d extraction_failed=%d in %.1fs%s",
            summary.screened, summary.filtered, summary.fetched, summary.fetch_failed,
            summary.fetch_retry, summary.extracted, summary.incidents_created, summary.corroborated,
            summary.discarded, summary.extraction_failed, summary.seconds,
            f" (extraction skipped: {summary.extraction_skipped})" if summary.extraction_skipped else "",
        )
        return summary

    @contextmanager
    def _lock(self) -> Iterator[bool]:
        """Session-level advisory lock on its own AUTOCOMMIT connection (no open transaction)."""
        conn = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        acquired = False
        try:
            acquired = bool(conn.execute(text("SELECT pg_try_advisory_lock(CAST(:k AS BIGINT))"), {"k": LOCK_KEY}).scalar())
            yield acquired
        finally:
            try:
                if acquired:
                    conn.execute(text("SELECT pg_advisory_unlock(CAST(:k AS BIGINT))"), {"k": LOCK_KEY})
            except Exception:  # noqa: BLE001
                conn.invalidate()  # closing the connection releases the lock
            finally:
                conn.close()

    # ------------------------------------------------------------ stage 1
    def screen_pending(self, summary: PipelineSummary) -> None:
        """Keyword-screen ``pending`` items and redact their headline and excerpt."""
        with self._sessions.begin() as db:
            items = db.scalars(
                select(SourceItem)
                .where(SourceItem.processing_status == ProcessingStatus.PENDING.value)
                .order_by(SourceItem.received_at)
                .limit(SCREEN_BATCH)
                .with_for_update(skip_locked=True)
            ).all()
            for item in items:
                result = screen(item.title_redacted, item.excerpt_redacted)
                title = redact(item.title_redacted).text or "Untitled"
                excerpt = redact(item.excerpt_redacted).text or None
                item.title_redacted, item.excerpt_redacted = title, excerpt
                item.source_metadata = {**item.source_metadata, "redaction": "applied"}
                item.screen_reason = result.reason
                item.source_metadata = {
                    **item.source_metadata,
                    "screening": {
                        "categories": list(result.candidate_categories),
                        "geographical_relevance": result.geographical_relevance,
                        "score": result.screening_score,
                        "reason_code": result.screening_reason_code,
                    },
                }
                if result.relevant and self._enabled_categories and not (
                    self._enabled_categories & set(result.candidate_categories)
                ):
                    item.screen_reason = "filtered: category not enabled (" + ", ".join(result.candidate_categories) + ")"
                    item.source_metadata["screening"]["reason_code"] = "category_not_enabled"
                    item.processing_status = ProcessingStatus.FILTERED.value
                    summary.filtered += 1
                elif result.relevant:
                    summary.screened += 1
                    if _is_social_post(item) and not item.source_metadata.get("linked_article_url"):
                        self._use_post_text(item)  # the post is the content: nothing to fetch
                        summary.fetched += 1
                    else:
                        item.processing_status = ProcessingStatus.SCREENED.value
                else:
                    item.processing_status = ProcessingStatus.FILTERED.value
                    summary.filtered += 1

    @staticmethod
    def _use_post_text(item: SourceItem) -> None:
        """Social post: its (already redacted) text stands in for the article. Moves it to ``fetched``."""
        text = item.excerpt_redacted or item.title_redacted
        item.article_text_redacted = text
        item.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        item.fetch_status = FetchStatus.OK.value
        item.fetch_error = None
        item.fetched_at = _now()
        item.processing_status = ProcessingStatus.FETCHED.value

    # ------------------------------------------------------------ stage 2
    def fetch_screened(self, summary: PipelineSummary) -> None:
        """Fetch, read and redact the full article for ``screened`` items."""
        with self._sessions() as db:
            queue = db.execute(
                select(SourceItem.id, SourceItem.canonical_url, SourceItem.source_metadata)
                .where(SourceItem.processing_status == ProcessingStatus.SCREENED.value)
                .order_by(SourceItem.received_at)
                .limit(self._batch)
            ).all()
        for item_id, url, metadata in queue:
            # A social post that links to an external article is read together with that article.
            target = (metadata or {}).get("linked_article_url") or url or (metadata or {}).get("url")
            try:
                if not target:
                    raise ArticleFetchError("item has no article URL")
                article = self._fetch_article(target)
            except ArticleFetchError as exc:
                self._record_fetch_failure(item_id, str(exc), transient=exc.transient, summary=summary)
            except Exception as exc:  # noqa: BLE001 - one bad page must not stop the batch
                self._record_fetch_failure(item_id, safe_error_message(exc), transient=False, summary=summary)
            else:
                if self._store_article(item_id, article):
                    summary.fetched += 1

    def _store_article(self, item_id: Any, article: Any) -> bool:
        redacted = redact(article.text)
        with self._sessions.begin() as db:
            item = self._lock_item(db, item_id, ProcessingStatus.SCREENED)
            if item is None:
                return False
            if _is_social_post(item) and item.excerpt_redacted:
                # the post, then the article it links to
                redacted_text = item.excerpt_redacted + "\n\n" + redacted.text
            else:
                redacted_text = redacted.text
            item.article_text_redacted = redacted_text
            item.content_hash = hashlib.sha256(redacted_text.encode("utf-8")).hexdigest()
            item.fetch_status = FetchStatus.OK.value
            item.fetch_error = None
            item.fetched_at = _now()
            item.processing_status = ProcessingStatus.FETCHED.value
            item.source_metadata = {
                **item.source_metadata,
                "article_url": article.url,
                "article_word_count": article.word_count,
                "redaction": "applied",
                "redaction_counts": redacted.counts,
            }
        return True

    def _record_fetch_failure(self, item_id: Any, message: str, *, transient: bool, summary: PipelineSummary) -> None:
        message = safe_error_message(message)
        with self._sessions.begin() as db:
            item = self._lock_item(db, item_id, ProcessingStatus.SCREENED)
            if item is None:
                return
            attempts = int(item.source_metadata.get("fetch_attempts", 0)) + 1
            item.source_metadata = {**item.source_metadata, "fetch_attempts": attempts}
            item.fetch_error = message
            if transient and attempts < self._max_attempts:
                summary.fetch_retry += 1  # stays "screened": tried again next cycle
                return
            if _is_social_post(item) and item.excerpt_redacted:
                # The linked page is unreadable, but the post itself is still a report: use it alone.
                item.source_metadata = {**item.source_metadata, "linked_article": "unreadable"}
                self._use_post_text(item)
                summary.fetched += 1
                return
            item.fetch_status = FetchStatus.FAILED.value
            item.fetched_at = _now()
            item.processing_status = ProcessingStatus.FETCH_FAILED.value
            summary.fetch_failed += 1
        log.info("Article not retrievable (%s): %s", item_id, message)

    # ------------------------------------------------------------ stage 3
    def extract_fetched(self, summary: PipelineSummary) -> None:
        """Send ``fetched`` articles to the model and store candidate incidents."""
        if self._extractor is None:
            summary.extraction_skipped = "no extractor configured (OPENAI_API_KEY not set)"
            return
        with self._sessions() as db:
            ids = db.scalars(
                select(SourceItem.id)
                .where(SourceItem.processing_status == ProcessingStatus.FETCHED.value)
                .order_by(SourceItem.received_at)
                .limit(self._batch)
            ).all()
        for item_id in ids:
            try:
                if self._extract_one(item_id, summary) == "unavailable":
                    summary.extraction_skipped = "extractor unavailable (credentials rejected)"
                    break
            except Exception as exc:  # noqa: BLE001 - e.g. a database hiccup; keep going
                message = safe_error_message(exc)
                summary.errors.append(message)
                log.warning("Extraction of %s failed unexpectedly: %s", item_id, message)

    def _extract_one(self, item_id: Any, summary: PipelineSummary) -> str:
        assert self._extractor is not None
        with self._sessions.begin() as db:
            item = db.get(SourceItem, item_id)
            if item is None or item.processing_status != ProcessingStatus.FETCHED.value:
                return "skipped"
            if not item.article_text_redacted:  # defensive: never extract from title/excerpt alone
                item.processing_status = ProcessingStatus.FETCH_FAILED.value
                item.fetch_status = FetchStatus.FAILED.value
                item.fetch_error = "no stored article text"
                return "skipped"
            duplicate_of = self._duplicate_of(db, item)
            if duplicate_of is not None:
                item.processing_status = ProcessingStatus.DISCARDED.value
                item.source_metadata = {**item.source_metadata, "discard_reason": f"duplicate_content_of:{duplicate_of}"}
                summary.discarded += 1
                return "duplicate"
            source = db.get(Source, item.source_id)
            payload = ExtractionInput(
                source_name=source.name if source else "unknown",
                title=item.title_redacted,
                published=item.published_at,
                text=item.article_text_redacted,
            )
            attempts = db.scalar(
                select(func.count()).select_from(ExtractionRun).where(
                    ExtractionRun.source_item_id == item.id,
                    ExtractionRun.status == ExtractionStatus.FAILED.value,
                )
            ) or 0
        # -- no transaction is open while the model works --
        try:
            output = self._extractor.extract(payload)
        except ExtractorUnavailable as exc:
            log.error("Extraction stopped: %s", exc)
            return "unavailable"
        except ExtractionError as exc:
            self._record_extraction_failure(item_id, str(exc), exc.retryable, attempts, summary)
            return "failed"
        return self._save_extraction(item_id, output, summary)

    @staticmethod
    def _duplicate_of(db: Session, item: SourceItem) -> Any:
        """Another item with identical redacted text that was already extracted (syndication)."""
        if not item.content_hash:
            return None
        return db.scalar(
            select(SourceItem.id)
            .join(ExtractionRun, ExtractionRun.source_item_id == SourceItem.id)
            .where(
                SourceItem.content_hash == item.content_hash,
                SourceItem.id != item.id,
                ExtractionRun.status == ExtractionStatus.SUCCEEDED.value,
            )
            .limit(1)
        )

    def _record_extraction_failure(
        self, item_id: Any, message: str, retryable: bool, attempts: int, summary: PipelineSummary
    ) -> None:
        with self._sessions.begin() as db:
            item = self._lock_item(db, item_id, ProcessingStatus.FETCHED)
            if item is None:
                return
            db.add(
                ExtractionRun(
                    source_item_id=item.id,
                    model_name=self._extractor.model_name,  # type: ignore[union-attr]
                    status=ExtractionStatus.FAILED.value,
                    error_message=safe_error_message(message),
                    completed_at=_now(),
                )
            )
            if retryable and attempts + 1 < self._max_attempts:
                summary.extraction_retry += 1  # stays "fetched": tried again next cycle
            else:
                item.processing_status = ProcessingStatus.FAILED.value
                summary.extraction_failed += 1

    def _save_extraction(self, item_id: Any, output: ExtractionOutput, summary: PipelineSummary) -> str:
        result = output.result
        with self._sessions.begin() as db:
            item = self._lock_item(db, item_id, ProcessingStatus.FETCHED)
            if item is None:
                return "skipped"
            intelligence = output.intelligence
            stored_output = result.model_dump(mode="json")
            if intelligence is not None:
                stored_output["intelligence"] = intelligence.model_dump(mode="json")
            run = ExtractionRun(
                source_item_id=item.id,
                model_name=output.model,
                model_version=output.model,
                prompt_version=output.prompt_version,
                extraction_output=stored_output,
                extraction_confidence=result.confidence,
                status=ExtractionStatus.SUCCEEDED.value,
                input_tokens=output.input_tokens,
                output_tokens=output.output_tokens,
                completed_at=_now(),
            )
            db.add(run)
            db.flush()
            summary.extracted += 1

            record = None
            if intelligence is not None:
                if not intelligence.is_transport_relevant or intelligence.classification_confidence < self._min_confidence:
                    reason = "not_transport_relevant" if not intelligence.is_transport_relevant else "low_confidence"
                    return self._discard(item, reason, summary)
                record = store_intelligence(db, item, run, intelligence, extraction_version=output.prompt_version)
                summary.intelligence_records += 1

            if not result.is_road_incident or result.confidence < self._min_confidence:
                if record is not None:
                    # Policy, statistics, projects, campaigns...: a reviewable record, never an incident.
                    db.add(self._record_audit(record, item, run, output))
                    item.processing_status = ProcessingStatus.PROCESSED.value
                    return "processed"
                reason = "not_a_road_incident" if not result.is_road_incident else "low_confidence"
                return self._discard(item, reason, summary)

            source = db.get(Source, item.source_id)
            incident, created = self._attach_incident(db, item, result, source.verification_tier if source else "unverified")
            if record is not None:
                record.incident_id = incident.id  # CHECK: only actionable events may be linked
                db.add(self._record_audit(record, item, run, output))
            db.add(
                AuditEvent(
                    actor_user_id=None,  # system action; no personal data in details
                    action="incident.candidate_created" if created else "incident.evidence_added",
                    entity_type="incident",
                    entity_id=incident.id,
                    details={
                        "source_item_id": str(item.id),
                        "extraction_run_id": str(run.id),
                        "model": output.model,
                        "prompt_version": output.prompt_version,
                        "confidence": result.confidence,
                    },
                )
            )
            item.processing_status = ProcessingStatus.PROCESSED.value
            if created:
                summary.incidents_created += 1
            else:
                summary.corroborated += 1
            return "processed"

    @staticmethod
    def _discard(item: SourceItem, reason: str, summary: PipelineSummary) -> str:
        item.processing_status = ProcessingStatus.DISCARDED.value
        item.source_metadata = {**item.source_metadata, "discard_reason": reason}
        summary.discarded += 1
        return "discarded"

    @staticmethod
    def _record_audit(record: Any, item: SourceItem, run: ExtractionRun, output: ExtractionOutput) -> AuditEvent:
        return AuditEvent(
            actor_user_id=None,  # system action; no personal data in details
            action="intelligence.candidate_created",
            entity_type="intelligence_record",
            entity_id=record.id,
            details={
                "source_item_id": str(item.id),
                "extraction_run_id": str(run.id),
                "category": record.primary_category,
                "record_kind": record.record_kind,
                "model": output.model,
                "prompt_version": output.prompt_version,
            },
        )

    def _attach_incident(
        self, db: Session, item: SourceItem, result: ExtractionResult, tier: str
    ) -> tuple[Incident, bool]:
        """Add evidence to a matching open incident, or create a new ``candidate``."""
        occurred_at = result.occurred_at(item.published_at)
        existing = self._find_matching_incident(db, result, occurred_at)
        if existing is not None:
            db.add(
                IncidentEvidence(
                    incident_id=existing.id, source_item_id=item.id, evidence_role=EvidenceRole.CORROBORATING.value
                )
            )
            if existing.credibility_score is not None:
                score = existing.credibility_score
                existing.credibility_score = round(max(score, min(CORROBORATION_CAP, score + CORROBORATION_BONUS)), 2)
            return existing, False

        reference_time = occurred_at or item.published_at or _now()
        for _ in range(5):  # reference codes are random; retry on the (unlikely) collision
            incident = Incident(
                reference_code=_new_reference_code(reference_time),
                incident_type=result.incident_type.value,
                severity=result.severity.value,
                location_text=result.location_text,
                occurred_at=occurred_at,
                credibility_score=_credibility(result.confidence, tier),
                review_priority=SEVERITY_PRIORITY[result.severity.value],
                status=IncidentStatus.CANDIDATE.value,  # never approved or published here
            )
            try:
                with db.begin_nested():
                    db.add(incident)
                    db.flush()
            except IntegrityError:
                continue
            db.add(
                IncidentEvidence(
                    incident_id=incident.id, source_item_id=item.id, evidence_role=EvidenceRole.PRIMARY.value
                )
            )
            return incident, True
        raise RuntimeError("could not generate a unique incident reference code")

    @staticmethod
    def _find_matching_incident(db: Session, result: ExtractionResult, occurred_at: datetime | None) -> Incident | None:
        """Same type, same place (case-insensitive) and within a day: very likely the same event."""
        if not result.location_text or occurred_at is None:
            return None
        return db.scalars(
            select(Incident)
            .where(
                Incident.incident_type == result.incident_type.value,
                func.lower(Incident.location_text) == result.location_text.lower(),
                Incident.occurred_at.between(occurred_at - DUPLICATE_WINDOW, occurred_at + DUPLICATE_WINDOW),
                Incident.status.not_in([IncidentStatus.REJECTED.value, IncidentStatus.ARCHIVED.value]),
            )
            .order_by(Incident.created_at)
            .limit(1)
        ).first()

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _lock_item(db: Session, item_id: Any, expected: ProcessingStatus) -> SourceItem | None:
        """Row-lock the item and confirm nobody else moved it on while we worked without a transaction."""
        item = db.scalar(select(SourceItem).where(SourceItem.id == item_id).with_for_update())
        if item is None or item.processing_status != expected.value:
            return None
        return item
