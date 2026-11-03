"""Alembic migration behaviour, exercised on the disposable test database."""

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.core.database import Base
from conftest import alembic_config
from schema_constants import EXPECTED_TABLES

pytestmark = pytest.mark.usefixtures("migrated_engine")


def _script(test_database_url) -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config(test_database_url))


def _current(engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def test_there_is_a_single_migration_head(test_database_url):
    assert len(_script(test_database_url).get_heads()) == 1


def test_database_is_at_the_latest_revision(migrated_engine, test_database_url):
    assert _current(migrated_engine) == _script(test_database_url).get_current_head()


def test_upgrading_when_already_at_head_is_a_safe_no_op(migrated_engine, test_database_url):
    head = _script(test_database_url).get_current_head()
    command.upgrade(alembic_config(test_database_url), "head")
    command.upgrade(alembic_config(test_database_url), "head")
    assert _current(migrated_engine) == head
    assert set(inspect(migrated_engine).get_table_names()) - {"alembic_version", "spatial_ref_sys"} == EXPECTED_TABLES


def test_models_and_migration_describe_the_same_schema(migrated_engine):
    """Equivalent of `alembic check`: autogenerate must find nothing to change."""

    def include_object(obj, name, type_, reflected, compare_to):
        return not (type_ == "table" and name in {"spatial_ref_sys", "geometry_columns", "geography_columns"})

    with migrated_engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "include_object": include_object}
        )
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"models and migration are out of sync: {diff}"


def test_postgis_tables_are_ignored_by_autogenerate(migrated_engine):
    """spatial_ref_sys exists in the DB but is not an application table."""
    assert "spatial_ref_sys" in inspect(migrated_engine).get_table_names()
    assert "spatial_ref_sys" not in Base.metadata.tables


def test_downgrade_removes_application_objects_but_keeps_postgis(migrated_engine, test_database_url):
    cfg = alembic_config(test_database_url)
    try:
        command.downgrade(cfg, "base")
        remaining = set(inspect(migrated_engine).get_table_names())
        assert not (remaining & EXPECTED_TABLES)
        with migrated_engine.connect() as conn:
            assert conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")).scalar() == 1
            leftover_functions = conn.execute(
                text("SELECT proname FROM pg_proc WHERE proname LIKE 'saferoutezw\\_%'")
            ).all()
        assert leftover_functions == []
    finally:
        command.upgrade(cfg, "head")  # always leave the test database at head
    assert _current(migrated_engine) == _script(test_database_url).get_current_head()
