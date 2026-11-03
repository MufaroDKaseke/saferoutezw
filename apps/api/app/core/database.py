"""SQLAlchemy engine, session factory and declarative base.

Importing this module (or any model) never opens a connection: the engine is
created lazily on first use. Schema changes are made only through Alembic.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# Deterministic constraint names keep Alembic autogeneration and downgrades stable.
# Multi-column unique constraints and composite foreign keys are named explicitly.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


@lru_cache
def get_engine() -> Engine:
    """Return the shared engine, built from settings on first use."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        connect_args={"connect_timeout": settings.postgres_connect_timeout},
        pool_pre_ping=True,  # transparently replace connections dropped by the server
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    Uncommitted work is rolled back when the session closes, so handlers must
    call ``session.commit()`` explicitly.
    """
    with get_session_factory()() as session:
        yield session
