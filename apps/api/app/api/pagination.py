"""Bounded, server-side pagination shared by every list endpoint."""

from __future__ import annotations

from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=MAX_PAGE_SIZE)


class PageParams(BaseModel):
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


Pagination = Annotated[PageParams, Depends(page_params)]


def count_rows(session: Session, query: Select) -> int:
    """COUNT(*) over ``query`` without its ordering."""
    return session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


def paginate(session: Session, query: Select, params: PageParams) -> tuple[list, int]:
    """Return (rows, total) for one page of an already-ordered ``query``."""
    total = count_rows(session, query)
    rows = session.execute(query.limit(params.page_size).offset(params.offset)).all()
    return rows, total
