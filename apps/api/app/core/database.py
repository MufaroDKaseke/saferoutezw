"""Lazy SQLAlchemy engine configuration; no tables or migrations are created."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    database_url = get_settings().database_url
    if database_url is None:
        raise RuntimeError("Set DATABASE_URL in the root .env file before using the database.")
    return create_engine(database_url.get_secret_value(), pool_pre_ping=True)
