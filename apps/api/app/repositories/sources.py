"""Data-source and ingestion-run queries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import IngestionRun, Source, SourceItem
from app.models.enums import IngestionStatus
from app.repositories.incidents import _like
from app.schemas.source import IngestionRunOut, SourceOut


def source_list_query(
    *, q: str | None = None, kind: str | None = None, enabled: bool | None = None
) -> Select:
    query = select(Source)
    if q:
        query = query.where(Source.name.ilike(_like(q.strip())))
    if kind:
        query = query.where(Source.kind == kind)
    if enabled is not None:
        query = query.where(Source.enabled.is_(enabled))
    return query.order_by(func.lower(Source.name), Source.id)


def build_sources(session: Session, sources: list[Source]) -> list[SourceOut]:
    ids = [s.id for s in sources]
    if not ids:
        return []
    since = datetime.now(UTC) - timedelta(days=7)
    failing = (IngestionRun.status.in_((IngestionStatus.FAILED.value, IngestionStatus.PARTIAL.value)))
    stats = {
        row[0]: row
        for row in session.execute(
            select(
                IngestionRun.source_id,
                func.max(IngestionRun.started_at),
                func.max(IngestionRun.completed_at).filter(
                    IngestionRun.status == IngestionStatus.SUCCEEDED.value
                ),
                func.count().filter(failing, IngestionRun.started_at >= since),
            )
            .where(IngestionRun.source_id.in_(ids))
            .group_by(IngestionRun.source_id)
        )
    }
    last_errors = dict(
        session.execute(
            select(IngestionRun.source_id, IngestionRun.error_message)
            .where(IngestionRun.source_id.in_(ids), IngestionRun.error_message.is_not(None))
            .order_by(IngestionRun.source_id, IngestionRun.started_at.desc())
            .distinct(IngestionRun.source_id)
        ).all()
    )
    articles = dict(
        session.execute(
            select(SourceItem.source_id, func.count())
            .where(SourceItem.source_id.in_(ids))
            .group_by(SourceItem.source_id)
        ).all()
    )
    out = []
    for s in sources:
        _, polled, success, errors = stats.get(s.id, (None, None, None, 0))
        out.append(
            SourceOut(
                id=s.id,
                name=s.name,
                kind=s.kind,
                feed_url=s.feed_url,
                enabled=s.enabled,
                poll_interval_seconds=s.poll_interval_seconds,
                verification_tier=s.verification_tier,
                rights_notes=s.rights_notes,
                last_polled_at=polled,
                last_success_at=success,
                last_error=last_errors.get(s.id),
                error_count_7d=errors or 0,
                article_count=articles.get(s.id, 0),
            )
        )
    return out


def runs_query(*, source_id: uuid.UUID | None = None, status: str | None = None) -> Select:
    query = select(IngestionRun, Source.name).join(Source, Source.id == IngestionRun.source_id)
    if source_id:
        query = query.where(IngestionRun.source_id == source_id)
    if status:
        query = query.where(IngestionRun.status == status)
    return query.order_by(IngestionRun.started_at.desc(), IngestionRun.id)


def build_runs(rows: list[Any]) -> list[IngestionRunOut]:
    return [
        IngestionRunOut(
            id=r.id,
            source_id=r.source_id,
            source_name=name,
            started_at=r.started_at,
            completed_at=r.completed_at,
            status=r.status,
            fetched_count=r.fetched_count,
            inserted_count=r.inserted_count,
            duplicate_count=r.duplicate_count,
            error_count=r.error_count,
            error_message=r.error_message,
        )
        for r, name in rows
    ]
