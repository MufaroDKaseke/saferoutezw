"""Dashboard aggregates. Counting rules are documented in ``app.schemas.dashboard``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Incident, IngestionRun, Source, SourceItem
from app.models.enums import IncidentStatus, ProcessingStatus
from app.repositories.sources import build_runs
from app.schemas.dashboard import ActivityPoint, DashboardActivity, DashboardSummary, MonthlyIncidentPoint, MonthlyIncidents

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
    candidates, pending, high_pending, oldest, approved = session.execute(
        select(
            func.count().filter(Incident.created_at >= since, Incident.created_at < until),
            func.count().filter(Incident.status.in_(OPEN_STATUSES)),
            func.count().filter(Incident.status.in_(OPEN_STATUSES), Incident.review_priority.in_(("high", "urgent"))),
            func.min(Incident.created_at).filter(Incident.status.in_(OPEN_STATUSES)),
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
        high_priority_pending=high_pending,
        oldest_pending_at=oldest,
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


HARARE = ZoneInfo("Africa/Harare")


def _month_starts(now: datetime, months: int) -> list[datetime]:
    """First instant of each of the last ``months`` calendar months in Zimbabwe time, oldest first."""
    local = now.astimezone(HARARE)
    year, month = local.year, local.month
    starts = []
    for back in range(months - 1, -1, -1):
        m = month - back
        y = year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        starts.append(datetime(y, m, 1, tzinfo=HARARE))
    return starts


def incidents_by_month(session: Session, months: int, now: datetime | None = None) -> MonthlyIncidents:
    """Road incidents per month by severity, rejected reports excluded."""
    starts = _month_starts(now or datetime.now(UTC), months)
    when = func.coalesce(Incident.occurred_at, Incident.created_at)
    month = func.date_trunc("month", func.timezone("Africa/Harare", when)).label("month")
    rows = session.execute(
        select(month, Incident.severity, func.count(), func.count().filter(Incident.status.in_(APPROVED_STATUSES)))
        .where(when >= starts[0], Incident.status != IncidentStatus.REJECTED.value)
        .group_by("month", Incident.severity)
    ).all()
    table: dict[datetime, dict[str, int]] = {}
    for bucket, severity, count, verified in rows:
        key = bucket.replace(tzinfo=HARARE)  # date_trunc of local time: a naive local month start
        entry = table.setdefault(key, {"fatal": 0, "serious": 0, "minor": 0, "unknown": 0, "verified": 0})
        entry[severity if severity in entry else "unknown"] += count
        entry["verified"] += verified
    points = []
    for start in starts:
        e = table.get(start, {"fatal": 0, "serious": 0, "minor": 0, "unknown": 0, "verified": 0})
        points.append(
            MonthlyIncidentPoint(
                month_start=start.astimezone(UTC),
                total=e["fatal"] + e["serious"] + e["minor"] + e["unknown"],
                **e,
            )
        )
    return MonthlyIncidents(
        months=months,
        points=points,
        total=sum(p.total for p in points),
        verified_total=sum(p.verified for p in points),
    )
