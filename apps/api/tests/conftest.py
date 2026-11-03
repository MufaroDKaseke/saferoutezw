"""Shared fixtures.

Database tests run against a separate, disposable test database
(``POSTGRES_TEST_DB``, default ``saferoutezw_test``). It is created on demand,
migrated with Alembic, and truncated between tests. The configured development
database is never touched, and the guard below refuses any test database whose
name does not end in ``_test``.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import Base

import app.models  # noqa: F401  - make sure Base.metadata is complete

API_ROOT = Path(__file__).resolve().parents[1]


def alembic_config(url: URL) -> Config:
    """Alembic config that targets ``url`` without writing it to any file."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.attributes["sqlalchemy_url"] = url
    return cfg


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def test_database_url(settings: Settings) -> URL:
    if not settings.postgres_user or settings.postgres_password is None:
        pytest.skip("POSTGRES_USER / POSTGRES_PASSWORD are not configured in .env")
    name = settings.postgres_test_db
    if name == settings.postgres_db or not name.endswith("_test"):
        pytest.fail(
            f"Refusing to run destructive tests against database {name!r}: "
            "POSTGRES_TEST_DB must differ from POSTGRES_DB and end with '_test'."
        )
    return settings.test_database_url


@pytest.fixture(scope="session")
def migrated_engine(settings: Settings, test_database_url: URL) -> Iterator[Engine]:
    """Test database, created if missing and migrated to Alembic head."""
    admin = create_engine(settings.build_database_url("postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": settings.postgres_test_db}
            ).scalar()
            if not exists:
                quoted = admin.dialect.identifier_preparer.quote(settings.postgres_test_db)
                conn.execute(text(f"CREATE DATABASE {quoted} ENCODING 'UTF8'"))
            has_postgis = conn.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
            ).scalar()
    except OperationalError as exc:
        pytest.skip(f"PostgreSQL is not reachable: {type(exc.orig).__name__}")
    finally:
        admin.dispose()

    if not has_postgis:
        pytest.fail(
            "PostGIS is not installed on the PostgreSQL server (pg_available_extensions has no "
            "'postgis'). Install the PostGIS bundle matching your PostgreSQL version, then re-run."
        )

    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_engine: Engine, test_database_url: URL) -> Iterator[Session]:
    """A session on a clean database. TRUNCATE skips row triggers, so append-only tables reset too."""
    # Make sure a previous test (e.g. a downgrade round-trip) left the schema at head.
    command.upgrade(alembic_config(test_database_url), "head")
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    with Session(migrated_engine) as s:
        yield s
        s.rollback()


@contextmanager
def db_error(session: Session, sqlstate: str) -> Iterator[None]:
    """Expect the enclosed statements to fail with an integrity error of ``sqlstate``.

    Runs inside a SAVEPOINT so fixtures created earlier in the test survive.
    Common codes: 23505 unique, 23503 foreign key, 23514 check, 23001 restrict.
    """
    savepoint = session.begin_nested()
    try:
        yield
        session.flush()
    except IntegrityError as exc:
        savepoint.rollback()
        actual = getattr(exc.orig, "sqlstate", None)
        assert actual == sqlstate, f"expected SQLSTATE {sqlstate}, got {actual}: {exc.orig}"
    else:
        savepoint.rollback()
        pytest.fail(f"expected a database error with SQLSTATE {sqlstate}, but the statement succeeded")


@pytest.fixture(name="db_error")
def db_error_fixture():
    return db_error
