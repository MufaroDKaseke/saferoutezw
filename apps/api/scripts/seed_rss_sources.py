"""Add the configured news feeds to the `sources` table (safe to run repeatedly).

    cd apps/api
    python scripts/seed_rss_sources.py

Run `alembic upgrade head` first. Existing sources are left exactly as they are.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # works without `pip install -e`

from app.core.database import get_session_factory  # noqa: E402
from app.ingestion.sources import seed_rss_sources  # noqa: E402


def main() -> int:
    with get_session_factory()() as db:
        added = seed_rss_sources(db)
        db.commit()
    print(f"Added {added} new RSS source(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
