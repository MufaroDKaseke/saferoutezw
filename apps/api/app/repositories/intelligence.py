"""Read-side queries for intelligence records, statistics, trends and published outputs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Source, SourceItem, User
from app.models.intelligence import (
    IntelligenceRecord,
    IntelligenceReview,
    IntelligenceVersion,
    PublicationOutput,
    StatisticalObservation,
)
from app.repositories.incidents import _like
from app.repositories.public import PUBLIC_SOURCE_KINDS
from app.schemas.intelligence_api import (
    CategoriesOut,
    CategoryCount,
    Citation,
    CorridorCount,
    InsightsOut,
    IntelligenceDetail,
    IntelligenceSummary,
    ObservationOut,
    OutputOut,
    OverviewOut,
    PublicStatistic,
    PublicTransportItem,
    IntelligenceReviewOut,
    StatisticsOut,
    StatisticsSeries,
    TopicGroup,
    TrendPoint,
    TrendsOut,
    VersionOut,
)
from app.schemas.public import PublicSource
from app.taxonomy import (
    ALLOWED_OUTPUTS,
    CATEGORY_LABELS,
    SUBTYPES,
    TAXONOMY_VERSION,
    GeographicScope,
    PrimaryCategory,
    RecordKind,
    RecordStatus,
    TemporalStatus,
)

AWAITING = (RecordStatus.CANDIDATE.value, RecordStatus.UNDER_REVIEW.value)
MIN_TREND_RECORDS = 30
MIN_CORRIDOR_RECORDS = 2

STATS_NOTE = (
    "Each figure keeps its own reporting period, coverage and source. Figures from different "
    "periods, sources or definitions are not added together, and figures extracted from news "
    "reports are not official national totals until verified by an editor."
)
TREND_CAVEAT = (
    "Counts of records ingested from news reports and other monitored sources. They describe "
    "what was reported and classified, not the true number of events, and are not comparable "
    "with official accident statistics."
)
INSIGHT_CAVEAT = (
    "Leads for editors, built from reviewed and unreviewed records. Verify against the cited "
    "sources before reporting; small samples do not establish a trend."
)
PUBLIC_STATS_NOTE = (
    "Published figures keep the period, coverage and source given by the reporting institution. "
    "They are not added together across periods or sources."
)


# --------------------------------------------------------------------------- list


@dataclass
class IntelligenceFilters:
    category: str | None = None
    subtype: str | None = None
    record_kind: str | None = None
    status: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    province: str | None = None
    source_id: uuid.UUID | None = None
    min_confidence: float | None = None
    q: str | None = None
    has_incident: bool | None = None
    topic_key: str | None = None


def _effective_date():
    return func.coalesce(IntelligenceRecord.event_date, func.date(IntelligenceRecord.created_at))


def list_query(f: IntelligenceFilters) -> Select:
    query = (
        select(IntelligenceRecord, Source, SourceItem)
        .join(SourceItem, SourceItem.id == IntelligenceRecord.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
    )
    r = IntelligenceRecord
    if f.category:
        query = query.where(r.primary_category == f.category)
    if f.subtype:
        query = query.where(r.primary_subtype == f.subtype)
    if f.record_kind:
        query = query.where(r.record_kind == f.record_kind)
    if f.status:
        query = query.where(r.status == f.status)
    if f.date_from:
        query = query.where(_effective_date() >= f.date_from)
    if f.date_to:
        query = query.where(_effective_date() <= f.date_to)
    if f.province:
        query = query.where(r.province.ilike(_like(f.province.strip())))
    if f.source_id:
        query = query.where(SourceItem.source_id == f.source_id)
    if f.min_confidence is not None:
        query = query.where(r.classification_confidence >= f.min_confidence)
    if f.q:
        term = _like(f.q.strip())
        query = query.where(or_(r.headline.ilike(term), r.neutral_summary.ilike(term)))
    if f.has_incident is not None:
        query = query.where(r.incident_id.is_not(None) if f.has_incident else r.incident_id.is_(None))
    if f.topic_key:
        query = query.where(r.topic_key == f.topic_key)
    return query.order_by(r.created_at.desc(), r.id)


def _outputs_for(session: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not ids:
        return {}
    rows = session.execute(
        select(PublicationOutput.record_id, PublicationOutput.output_type)
        .where(PublicationOutput.record_id.in_(ids), PublicationOutput.status == "published")
        .order_by(PublicationOutput.published_at)
    ).all()
    out: dict[uuid.UUID, list[str]] = {}
    for record_id, output_type in rows:
        out.setdefault(record_id, []).append(output_type)
    return out


def _summary(r: IntelligenceRecord, source: Source, item: SourceItem, outputs: list[str]) -> IntelligenceSummary:
    return IntelligenceSummary(
        id=r.id,
        source_item_id=r.source_item_id,
        headline=r.headline,
        summary=r.neutral_summary,
        primary_category=r.primary_category,
        primary_subtype=r.primary_subtype,
        secondary_categories=list(r.secondary_categories or []),
        record_kind=r.record_kind,
        temporal_status=r.temporal_status,
        geographic_scope=r.geographic_scope,
        classification_confidence=r.classification_confidence,
        status=r.status,
        event_date=r.event_date,
        province=r.province,
        district_or_town=r.district_or_town,
        road_name=r.road_name,
        publisher=source.name,
        source_url=item.canonical_url,
        source_published_at=item.published_at,
        incident_id=r.incident_id,
        needs_editorial_review=r.needs_editorial_review,
        topic_key=r.topic_key,
        published_outputs=outputs,
        created_at=r.created_at,
    )


def build_summaries(session: Session, rows: list[Any]) -> list[IntelligenceSummary]:
    outputs = _outputs_for(session, [r[0].id for r in rows])
    return [_summary(r, s, i, outputs.get(r.id, [])) for r, s, i in rows]


# --------------------------------------------------------------------------- detail


def observation_out(o: StatisticalObservation) -> ObservationOut:
    return ObservationOut(
        id=o.id, record_id=o.record_id, metric=o.metric, value=float(o.value), unit=o.unit,
        period_start=o.period_start, period_end=o.period_end, geographic_coverage=o.geographic_coverage,
        source_reference=o.source_reference, methodology=o.methodology,
        comparison_period=o.comparison_period, is_preliminary=o.is_preliminary,
        verification_status=o.verification_status,
    )


def get_row(session: Session, record_id: uuid.UUID) -> Any | None:
    return session.execute(
        select(IntelligenceRecord, Source, SourceItem)
        .join(SourceItem, SourceItem.id == IntelligenceRecord.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(IntelligenceRecord.id == record_id)
    ).first()


def build_detail(session: Session, row: Any) -> IntelligenceDetail:
    r, source, item = row
    versions = session.execute(
        select(IntelligenceVersion, User.display_name)
        .join(User, User.id == IntelligenceVersion.created_by)
        .where(IntelligenceVersion.record_id == r.id)
        .order_by(IntelligenceVersion.version_number.desc())
    ).all()
    latest = versions[0][0].version_number if versions else 0
    numbers = {v.id: v.version_number for v, _ in versions}
    reviews = session.execute(
        select(IntelligenceReview, User.display_name)
        .join(User, User.id == IntelligenceReview.reviewer_id)
        .where(IntelligenceReview.record_id == r.id)
        .order_by(IntelligenceReview.reviewed_at.desc(), IntelligenceReview.id)
    ).all()
    outputs = session.scalars(
        select(PublicationOutput).where(PublicationOutput.record_id == r.id).order_by(PublicationOutput.published_at)
    ).all()
    observations = session.scalars(
        select(StatisticalObservation).where(StatisticalObservation.record_id == r.id)
        .order_by(StatisticalObservation.metric, StatisticalObservation.period_start, StatisticalObservation.id)
    ).all()
    published = [o.output_type for o in outputs if o.status == "published"]
    base = _summary(r, source, item, published).model_dump()
    return IntelligenceDetail(
        **base,
        location_description=r.location_description,
        country=r.country,
        source_attribution=r.source_attribution,
        taxonomy_version=r.taxonomy_version,
        extraction_version=r.extraction_version,
        details=r.details,
        quality=r.quality,
        citations=[Citation(source_name=source.name, source_kind=source.kind, title=item.title_redacted,
                            url=item.canonical_url, published_at=item.published_at)],
        observations=[observation_out(o) for o in observations],
        versions=[
            VersionOut(
                id=v.id, version_number=v.version_number, headline=v.headline, summary=v.summary,
                primary_category=v.primary_category, primary_subtype=v.primary_subtype,
                geographic_scope=v.geographic_scope, event_date=v.event_date, figures=v.figures,
                source_attribution=v.source_attribution, change_note=v.change_note,
                created_by_name=name, created_at=v.created_at, is_latest=v.version_number == latest,
            )
            for v, name in versions
        ],
        reviews=[
            IntelligenceReviewOut(id=rv.id, version_number=numbers.get(rv.version_id), decision=rv.decision,
                      notes=rv.notes, reviewer_name=name, reviewed_at=rv.reviewed_at)
            for rv, name in reviews
        ],
        outputs=[
            OutputOut(id=o.id, output_type=o.output_type, status=o.status,
                      version_number=numbers.get(o.version_id, 0), published_at=o.published_at,
                      withdrawn_at=o.withdrawn_at)
            for o in outputs
        ],
        allowed_outputs=list(ALLOWED_OUTPUTS[PrimaryCategory(r.primary_category)]),
    )


# --------------------------------------------------------------------------- categories / overview


def category_counts(session: Session) -> list[CategoryCount]:
    r = IntelligenceRecord
    rows = session.execute(
        select(
            r.primary_category,
            func.count(),
            func.count().filter(r.status.in_(AWAITING)),
            func.count().filter(r.status == RecordStatus.PUBLISHED.value),
        ).group_by(r.primary_category)
    ).all()
    found = {c: (t, a, p) for c, t, a, p in rows}
    return [
        CategoryCount(
            category=c.value, label=CATEGORY_LABELS[c.value], subtypes=list(SUBTYPES[c]),
            total=found.get(c.value, (0, 0, 0))[0], awaiting_review=found.get(c.value, (0, 0, 0))[1],
            published=found.get(c.value, (0, 0, 0))[2],
        )
        for c in PrimaryCategory
    ]


def categories(session: Session) -> CategoriesOut:
    return CategoriesOut(
        taxonomy_version=TAXONOMY_VERSION,
        categories=category_counts(session),
        record_kinds=[k.value for k in RecordKind],
        temporal_statuses=[t.value for t in TemporalStatus],
        geographic_scopes=[g.value for g in GeographicScope],
    )


def overview(session: Session) -> OverviewOut:
    awaiting = session.scalar(
        select(func.count()).select_from(IntelligenceRecord).where(IntelligenceRecord.status.in_(AWAITING))
    ) or 0
    published = dict(
        session.execute(
            select(PublicationOutput.output_type, func.count())
            .where(PublicationOutput.status == "published").group_by(PublicationOutput.output_type)
        ).all()
    )
    rows = session.execute(list_query(IntelligenceFilters()).limit(8)).all()
    latest = session.scalars(
        select(StatisticalObservation).where(StatisticalObservation.verification_status != "rejected")
        .order_by(StatisticalObservation.created_at.desc(), StatisticalObservation.id).limit(6)
    ).all()
    return OverviewOut(
        by_category=category_counts(session), awaiting_review=awaiting, published_by_output=published,
        recent=build_summaries(session, rows), latest_statistics=[observation_out(o) for o in latest],
    )


# --------------------------------------------------------------------------- statistics / trends / insights


def statistics(
    session: Session, *, metric: str | None, source: str | None, verified_only: bool,
    period_from: date | None, period_to: date | None, limit: int,
) -> StatisticsOut:
    o = StatisticalObservation
    query = select(o).where(o.verification_status != "rejected")
    if metric:
        query = query.where(o.metric.ilike(_like(metric.strip())))
    if source:
        query = query.where(o.source_reference.ilike(_like(source.strip())))
    if verified_only:
        query = query.where(o.verification_status == "verified")
    if period_from:
        query = query.where(or_(o.period_end.is_(None), o.period_end >= period_from))
    if period_to:
        query = query.where(or_(o.period_start.is_(None), o.period_start <= period_to))
    rows = session.scalars(
        query.order_by(o.metric, o.unit, o.geographic_coverage, o.period_start.nulls_last(), o.id).limit(limit)
    ).all()
    series: dict[tuple[str, str, str | None], list[ObservationOut]] = {}
    for obs in rows:  # one series per metric/unit/coverage; periods stay separate points
        series.setdefault((obs.metric, obs.unit, obs.geographic_coverage), []).append(observation_out(obs))
    return StatisticsOut(
        series=[StatisticsSeries(metric=m, unit=u, geographic_coverage=c, points=pts) for (m, u, c), pts in series.items()],
        note=STATS_NOTE,
    )


def trends(session: Session, *, months: int, category: str | None) -> TrendsOut:
    r = IntelligenceRecord
    since = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    since = (since - timedelta(days=31 * (months - 1))).replace(day=1)
    month = func.to_char(func.date_trunc("month", r.created_at), "YYYY-MM")
    query = select(month, r.primary_category, func.count()).where(r.created_at >= since)
    if category:
        query = query.where(r.primary_category == category)
    rows = session.execute(query.group_by(month, r.primary_category).order_by(month, r.primary_category)).all()
    total = sum(c for _, _, c in rows)
    return TrendsOut(
        basis="records classified from monitored news and social sources",
        months=months, total=total,
        points=[TrendPoint(month=m, category=c, count=n) for m, c, n in rows],
        sufficient_data=total >= MIN_TREND_RECORDS,
        caveat=TREND_CAVEAT,
    )


def insights(session: Session) -> InsightsOut:
    r = IntelligenceRecord
    topics = session.execute(
        select(
            r.topic_key, r.primary_category, func.count(), func.count(func.distinct(Source.id)),
            func.min(r.created_at), func.max(r.created_at),
        )
        .join(SourceItem, SourceItem.id == r.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(r.topic_key.is_not(None)).group_by(r.topic_key, r.primary_category)
        .having(func.count() >= 2).order_by(func.max(r.created_at).desc()).limit(20)
    ).all()
    groups = []
    for key, category, count, publishers, first, last in topics:
        heads = session.scalars(
            select(r.headline).where(r.topic_key == key).order_by(r.created_at.desc()).limit(5)
        ).all()
        groups.append(TopicGroup(topic_key=key, category=category, record_count=count,
                                 publisher_count=publishers, first_seen=first, last_seen=last, headlines=list(heads)))
    corridors = session.execute(
        select(r.road_name, r.primary_category, func.count())
        .where(r.road_name.is_not(None), r.primary_category.in_(["road_hazard", "traffic_disruption", "road_infrastructure"]))
        .group_by(r.road_name, r.primary_category).having(func.count() >= MIN_CORRIDOR_RECORDS)
        .order_by(func.count().desc(), r.road_name).limit(20)
    ).all()
    new_stats = session.scalars(
        select(StatisticalObservation)
        .where(StatisticalObservation.source_reference.is_not(None), StatisticalObservation.verification_status != "rejected")
        .order_by(StatisticalObservation.created_at.desc(), StatisticalObservation.id).limit(10)
    ).all()
    return InsightsOut(
        topic_groups=groups, corridors=[CorridorCount(road_name=n, category=c, count=k) for n, c, k in corridors],
        new_statistics=[observation_out(o) for o in new_stats], caveat=INSIGHT_CAVEAT,
    )


# --------------------------------------------------------------------------- public (published only)


def published_base(*output_types: str) -> Select:
    """Published outputs of approved versions. Nothing unreviewed or withdrawn is ever selected."""
    query = (
        select(PublicationOutput, IntelligenceVersion, IntelligenceRecord)
        .join(IntelligenceVersion, IntelligenceVersion.id == PublicationOutput.version_id)
        .join(IntelligenceRecord, IntelligenceRecord.id == PublicationOutput.record_id)
        .where(PublicationOutput.status == "published", IntelligenceRecord.status == RecordStatus.PUBLISHED.value)
    )
    if output_types:
        query = query.where(PublicationOutput.output_type.in_(output_types))
    return query.order_by(PublicationOutput.published_at.desc(), PublicationOutput.id)


def _public_sources(session: Session, record_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[PublicSource]]:
    if not record_ids:
        return {}
    rows = session.execute(
        select(IntelligenceRecord.id, Source.name, SourceItem.canonical_url)
        .join(SourceItem, SourceItem.id == IntelligenceRecord.source_item_id)
        .join(Source, Source.id == SourceItem.source_id)
        .where(IntelligenceRecord.id.in_(record_ids), Source.kind.in_(PUBLIC_SOURCE_KINDS))
    ).all()
    return {rid: [PublicSource(name=name, url=url)] for rid, name, url in rows}


def build_public_items(session: Session, rows: list[Any]) -> list[PublicTransportItem]:
    sources = _public_sources(session, [r[2].id for r in rows])
    return [
        PublicTransportItem(
            id=out.id, output_type=out.output_type, headline=v.headline, summary=v.summary,
            category=v.primary_category, subtype=v.primary_subtype, geographic_scope=v.geographic_scope,
            event_date=v.event_date, source_attribution=v.source_attribution,
            sources=sources.get(rec.id, []), published_at=out.published_at,
        )
        for out, v, rec in rows
    ]


def public_statistics(session: Session, *, metric: str | None, limit: int) -> list[PublicStatistic]:
    """Verified figures from records published as a statistical insight or dashboard source."""
    o = StatisticalObservation
    query = (
        select(o, PublicationOutput.id)
        .join(PublicationOutput, PublicationOutput.record_id == o.record_id)
        .join(IntelligenceRecord, IntelligenceRecord.id == o.record_id)
        .where(
            PublicationOutput.status == "published",
            PublicationOutput.output_type.in_(["statistical_insight", "dashboard_source"]),
            IntelligenceRecord.status == RecordStatus.PUBLISHED.value,
            o.verification_status == "verified",
        )
        .order_by(o.metric, o.period_start.nulls_last(), o.id)
        .limit(limit)
    )
    if metric:
        query = query.where(o.metric.ilike(_like(metric.strip())))
    return [
        PublicStatistic(
            metric=obs.metric, value=float(obs.value), unit=obs.unit, period_start=obs.period_start,
            period_end=obs.period_end, geographic_coverage=obs.geographic_coverage,
            source_reference=obs.source_reference, methodology=obs.methodology,
            is_preliminary=obs.is_preliminary, published_item_id=out_id,
        )
        for obs, out_id in session.execute(query).all()
    ]
