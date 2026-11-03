"""Database connectivity self-check.

Run from ``apps/api``::

    python -m app.core.db_check

Reports the target (never the password), server version, PostGIS status, the
current Alembic revision and how many application tables exist. Read-only.
Exit code 0 when the database is reachable, 1 otherwise.
"""

import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.models import Base

NOT_APPLICATION_TABLES = {"alembic_version", "spatial_ref_sys"}


def main() -> int:
    try:
        url = get_settings().database_url
    except RuntimeError as exc:
        print(f"Configuration error: {exc}")
        return 1

    print(f"Target   : {url.username}@{url.host}:{url.port}/{url.database}")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            print("Server   :", conn.execute(text("SELECT version()")).scalar_one().split(",")[0])

            enabled = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")).scalar()
            available = conn.execute(
                text("SELECT 1 FROM pg_available_extensions WHERE name = 'postgis'")
            ).scalar()
            if enabled:
                print("PostGIS  :", conn.execute(text("SELECT PostGIS_Version()")).scalar_one())
            elif available:
                print("PostGIS  : installed on the server but not enabled here (run: alembic upgrade head)")
            else:
                print("PostGIS  : NOT INSTALLED on this server - install the PostGIS bundle for your PostgreSQL version")

            tables = set(inspect(conn).get_table_names())
            revision = (
                conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                if "alembic_version" in tables
                else None
            )
            expected = set(Base.metadata.tables)
            present = (tables - NOT_APPLICATION_TABLES) & expected
            print(f"Migration: {revision or 'none applied yet'}")
            print(f"Tables   : {len(present)}/{len(expected)} application tables present")
    except SQLAlchemyError as exc:
        reason = str(getattr(exc, "orig", None) or exc).strip().splitlines()[0]
        print(f"Connection failed ({type(getattr(exc, 'orig', exc)).__name__}): {reason}")
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
