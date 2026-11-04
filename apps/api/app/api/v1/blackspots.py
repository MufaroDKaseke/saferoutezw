"""Historical blackspots and the safety-map feed (authenticated, read-only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AppSettings, DbSession, Reader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models.enums import RiskLevel
from app.repositories import blackspots as repo
from app.schemas.blackspot import BlackspotOut, MapData

router = APIRouter(tags=["blackspots"], responses=ERROR_RESPONSES)


@router.get("/blackspots", response_model=Page[BlackspotOut])
def list_blackspots(
    auth: Reader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200)] = None,
    risk_level: RiskLevel | None = None,
) -> Page[BlackspotOut]:
    query = repo.blackspot_list_query(q=q, risk_level=risk_level.value if risk_level else None)
    rows, total = paginate(db, query, pagination)
    counts = repo.nearby_counts(db, [r[0].id for r in rows])
    return Page(
        items=[repo.to_blackspot(r, counts) for r in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/blackspots/{blackspot_id}", response_model=BlackspotOut)
def get_blackspot(blackspot_id: uuid.UUID, auth: Reader, db: DbSession) -> BlackspotOut:
    row = repo.get_blackspot_row(db, blackspot_id)
    if row is None:
        raise not_found("BLACKSPOT_NOT_FOUND", "The requested blackspot was not found.")
    return repo.to_blackspot(row, repo.nearby_counts(db, [row[0].id]))


@router.get("/map", response_model=MapData)
def get_map_data(
    auth: Reader, db: DbSession, include_blackspots: bool = True
) -> MapData:
    """Markers for incidents with a firm position, plus historical blackspots."""
    return repo.build_map(db, include_blackspots)
