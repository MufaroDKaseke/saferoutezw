"""Alembic environment for SafeRouteZW.

* The database URL comes from ``app.core.config.Settings`` (POSTGRES_* in the
  root ``.env``), never from ``alembic.ini``, so no password is stored in
  configuration files or echoed to the terminal.
* ``target_metadata`` is ``Base.metadata`` with every model imported.
* PostGIS-owned objects are excluded so autogenerate never tries to manage them.

Programmatic callers (tests) may pass ``config.attributes["sqlalchemy_url"]``
(a SQLAlchemy ``URL``) or ``config.attributes["connection"]``.
"""

from logging.config import fileConfig

from alembic import context
from geoalchemy2 import alembic_helpers
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL

import app.models  # noqa: F401  - registers all 16 tables on Base.metadata
from app.core.config import DRIVERNAME, get_settings
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Tables/schemas created and owned by PostGIS and its companion extensions.
POSTGIS_TABLES = frozenset(
    {
        "spatial_ref_sys",
        "geometry_columns",
        "geography_columns",
        "raster_columns",
        "raster_overviews",
    }
)
POSTGIS_SCHEMAS = frozenset({"tiger", "tiger_data", "topology"})


def include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    """Keep PostGIS-managed objects out of autogenerate comparisons."""
    if type_ == "table":
        if name in POSTGIS_TABLES or getattr(obj, "schema", None) in POSTGIS_SCHEMAS:
            return False
    return True


def _online_url() -> URL:
    override = config.attributes.get("sqlalchemy_url")
    return override if override is not None else get_settings().database_url


def _configure_common() -> dict:
    return {
        "target_metadata": target_metadata,
        "include_object": include_object,
        "render_item": alembic_helpers.render_item,
        "compare_type": True,
    }


def run_migrations_offline() -> None:
    """Emit SQL without connecting (``alembic upgrade head --sql``).

    Only the dialect is needed, so no credentials are required or rendered.
    """
    context.configure(
        url=URL.create(DRIVERNAME),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_configure_common(),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, **_configure_common())
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(_online_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as conn:
            context.configure(connection=conn, **_configure_common())
            # PostgreSQL DDL is transactional: a failed migration leaves nothing behind.
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
