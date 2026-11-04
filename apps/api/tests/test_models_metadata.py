"""Schema-definition checks that need no database connection."""

import os
import subprocess
import sys
import warnings

import pytest
from sqlalchemy.orm import configure_mappers

from app.core.config import Settings
from app.core.database import Base
from app.core.geo import point_from_lat_lon

import app.models  # noqa: F401
from schema_constants import EXPECTED_TABLES

def test_exactly_the_sixteen_application_tables_are_modelled():
    assert set(Base.metadata.tables) == set(EXPECTED_TABLES)
    assert len(EXPECTED_TABLES) == 18


def test_every_table_has_a_uuid_primary_key_generated_by_postgres():
    for table in Base.metadata.sorted_tables:
        pk = list(table.primary_key.columns)
        assert [c.name for c in pk] == ["id"], table.name
        assert pk[0].type.__class__.__name__ == "Uuid", table.name
        assert pk[0].server_default is not None, f"{table.name}.id needs a server default"


def test_identifiers_fit_postgres_63_character_limit():
    for table in Base.metadata.sorted_tables:
        names = [c.name for c in table.constraints if c.name] + [i.name for i in table.indexes]
        for name in names:
            assert len(name) <= 63, f"{table.name}: {name} is {len(name)} chars"


def test_every_constraint_and_index_has_an_explicit_name():
    for table in Base.metadata.sorted_tables:
        for constraint in table.constraints:
            assert constraint.name, f"unnamed constraint on {table.name}: {constraint!r}"
        for index in table.indexes:
            assert index.name, f"unnamed index on {table.name}"


def test_geography_columns_are_gist_indexed():
    for table_name in ("incidents", "blackspots"):
        table = Base.metadata.tables[table_name]
        geom = table.c.geom
        assert geom.type.geometry_type == "POINT" and geom.type.srid == 4326
        assert geom.type.__class__.__name__ == "Geography"
        gist = [i for i in table.indexes if [c.name for c in i.columns] == ["geom"]]
        assert gist and gist[0].dialect_options["postgresql"]["using"] == "gist"


def test_mappers_configure_without_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        configure_mappers()


def test_importing_models_never_opens_a_connection():
    """Point at an unreachable server: importing everything must still succeed instantly."""
    env = {**os.environ, "POSTGRES_HOST": "127.0.0.1", "POSTGRES_PORT": "1",
           "POSTGRES_USER": "nobody", "POSTGRES_PASSWORD": "x"}
    code = (
        "import app.models, app.core.database as d; "
        "assert d.get_engine.cache_info().currsize == 0, 'engine was created at import'"
    )
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_database_url_escapes_special_characters_and_hides_password():
    password = "p@ss:w/rd#?%&=+ ünï"
    settings = Settings(
        _env_file=None, postgres_user="app", postgres_password=password,
        postgres_host="db.local", postgres_port=5433, postgres_db="saferoutezw",
    )
    url = settings.database_url
    assert url.drivername == "postgresql+psycopg"
    assert (url.host, url.port, url.database, url.username) == ("db.local", 5433, "saferoutezw", "app")
    assert url.password == password  # stored verbatim, escaped only when rendered
    assert password not in str(url) and "***" in str(url)  # str() masks the password
    rendered = url.render_as_string(hide_password=False)
    assert "@ss" not in rendered.split("@db.local")[0]  # the '@' inside the password is escaped
    assert settings.test_database_url.database == "saferoutezw_test"


def test_database_url_requires_credentials_but_settings_load_without_them():
    settings = Settings(_env_file=None, postgres_user=None, postgres_password=None)
    with pytest.raises(RuntimeError, match="POSTGRES_USER"):
        _ = settings.database_url


def test_point_helper_uses_longitude_latitude_order():
    point = point_from_lat_lon(latitude=-17.8292, longitude=31.0522)
    assert point.srid == 4326
    assert point.data == "POINT(31.0522 -17.8292)"  # x = longitude, y = latitude


@pytest.mark.parametrize("lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_point_helper_rejects_out_of_range_coordinates(lat, lon):
    with pytest.raises(ValueError):
        point_from_lat_lon(lat, lon)
