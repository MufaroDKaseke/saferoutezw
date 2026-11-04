"""Dashboard aggregates. Counting rules are documented in ``app.schemas.dashboard``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident, IngestionRun, Source, SourceItem
from app.models.enums import IncidentStatus, ProcessingStatus
from app.repositories.sources import build_runs
from app.schemas.dashboard import ActivityPoint, DashboardActivity, DashboardSummary

WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
NOT_SCREENED = (ProcessingStatus.PENDING.value, ProcessingStatus.FILTERED.value)
OPEN_STATUSES = (IncidentStatus.CANDIDATE.value, IncidentStatus.UNDER_REVIEW.value)
APPROVED_STATUSES = (IncidentStatus.APPROVED.value, IncidentStatus.PUBLISHED.value)
FAILED = (ProcessingStatus.FAILED.value, ProcessingStatus.FETCH_FAILED.value)


def summary(session: Session, range_: str, now: datetime | None = None) -> DashboardSummary:
    until = now or datetime.now(UTC)
    since = until - WINDOWS[range_]

    ingested, relevant = session.execute(
        select(
            func.count(),
            func.count().filter(SourceItem.processing_status.not_in(NOT_SCREENED)),
        ).where(SourceItem.received_at >= since, SourceItem.received_at < until)
    ).one()
    candidates, pending, approved = session.execute(
        select(
            func.count().filter(Incident.created_at >= since, Incident.created_at < until),
            func.count().filter(Incident.status.in_(OPEN_STATUSES)),
            func.count().filter(Incident.status.in_(APPROVED_STATUSES)),
        )
    ).one()
    pipeline = {s.value: 0 for s in ProcessingStatus}
    pipeline.update(
        dict(
            session.execute(
                select(SourceItem.processing_status, func.count()).group_by(SourceItem.processing_status)
            ).all()
        )
    )
    return DashboardSummary(
        range=range_,
        since=since,
        until=until,
        articles_ingested=ingested,
        relevant_articles=relevant,
        incident_candidates=candidates,
        pending_reviews=pending,
        approved_incidents=approved,
        failed_processing=sum(pipeline[s] for s in FAILED),
        pipeline=pipeline,
    )


def _buckets(range_: str, now: datetime) -> tuple[str, list[datetime]]:
    if range_ == "24h":
        end = now.replace(minute=0, second=0, microsecond=0)
        return "hour", [end - timedelta(hours=h) for h in range(23, -1, -1)]
    days = 7 if range_ == "7d" else 30
    end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return "day", [end - timedelta(days=d) for d in range(days - 1, -1, -1)]


def activity(session: Session, range_: str, now: datetime | None = None) -> DashboardActivity:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    unit, buckets = _buckets(range_, now)
    start = buckets[0]

    def bucket(column):
        # Truncate in UTC regardless of the database session time zone.
        return func.date_trunc(unit, func.timezone("UTC", column)).label("bucket")

    items = {
        row[0].replace(tzinfo=UTC): (row[1], row[2])
        for row in session.execute(
            select(
                bucket(SourceItem.received_at),
                func.count(),
                func.count().filter(SourceItem.processing_status.not_in(NOT_SCREENED)),
            )
            .where(SourceItem.received_at >= start)
            .group_by("bucket")
        )
    }
    incidents = {
        row[0].replace(tzinfo=UTC): row[1]
        for row in session.execute(
            select(bucket(Incident.created_at), func.count())
            .where(Incident.created_at >= start)
            .group_by("bucket")
        )
    }
    points = [
        ActivityPoint(
            bucket_start=b,
            articles=items.get(b, (0, 0))[0],
            relevant_articles=items.get(b, (0, 0))[1],
            incident_candidates=incidents.get(b, 0),
        )
        for b in buckets
    ]
    recent = session.execute(
        select(IngestionRun, Source.name)
        .join(Source, Source.id == IngestionRun.source_id)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id)
        .limit(10)
    ).all()
    return DashboardActivity(range=range_, bucket=unit, points=points, recent_runs=build_runs(recent))
