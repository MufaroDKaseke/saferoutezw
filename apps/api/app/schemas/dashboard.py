"""Dashboard responses.

Counting rules (all UTC, window = ``[since, until)`` for the chosen range):

* ``articles_ingested``   source items received in the window
* ``relevant_articles``   of those, items that passed the keyword screen
* ``incident_candidates`` incidents created in the window (any status)
* ``pending_reviews``     incidents now awaiting a decision (candidate or under_review)
* ``high_priority_pending`` pending reviews with high or urgent priority
* ``oldest_pending_at``    creation time of the oldest pending incident
* ``approved_incidents``  incidents now approved or published
* ``failed_processing``   source items now in failed or fetch_failed
The last three are current totals, not windowed.
"""

from __future__ import annotations

from typing import Literal

from app.schemas.common import ApiModel, UtcDatetime
from app.schemas.source import IngestionRunOut

Range = Literal["24h", "7d", "30d"]


class DashboardSummary(ApiModel):
    range: Range
    since: UtcDatetime
    until: UtcDatetime
    articles_ingested: int
    relevant_articles: int
    incident_candidates: int
    pending_reviews: int
    high_priority_pending: int
    oldest_pending_at: UtcDatetime | None
    approved_incidents: int
    failed_processing: int
    pipeline: dict[str, int]


class ActivityPoint(ApiModel):
    bucket_start: UtcDatetime
    articles: int
    relevant_articles: int
    incident_candidates: int


class DashboardActivity(ApiModel):
    range: Range
    bucket: Literal["hour", "day"]
    points: list[ActivityPoint]
    recent_runs: list[IngestionRunOut]


class MonthlyIncidentPoint(ApiModel):
    month_start: UtcDatetime  # first day of the month, Zimbabwe time (CAT), as a UTC instant
    total: int
    fatal: int
    serious: int
    minor: int
    unknown: int
    verified: int  # of ``total``, incidents an editor approved or published


class MonthlyIncidents(ApiModel):
    """Road incidents per month, by when they happened (falling back to when they were reported).

    Rejected reports are excluded: an editor decided they are not valid incidents.
    """

    months: int
    points: list[MonthlyIncidentPoint]
    total: int
    verified_total: int
