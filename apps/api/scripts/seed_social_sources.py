"""Sync the social-media allowlist from config/social_sources.yaml into the database.

    cd apps/api
    python scripts/seed_social_sources.py [--file path.yaml] [--dry-run]

Creates or updates the configuration of each listed account. Collection state (cursor, last
poll, status) is never touched, and accounts not in the file are left as they are.
Exit code: 0 ok; 1 the file had invalid entries (valid ones are still applied unless --dry-run).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import get_engine  # noqa: E402
from app.ingestion.social.seed import load_config, sync_social_sources  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="validate only; change nothing")
    args = parser.parse_args(argv)

    configs, errors = load_config(args.file)
    for error in errors:
        print(f"INVALID  {error}")
    if args.dry_run:
        for config in configs:
            print(f"valid    {config.name} ({config.platform.value}, {'enabled' if config.enabled else 'disabled'})")
        return 1 if errors else 0

    with Session(get_engine()) as db:
        result = sync_social_sources(db, configs)
        db.commit()
    errors += result.errors
    for error in result.errors:
        print(f"ERROR    {error}")
    print(f"created={len(result.created)} updated={len(result.updated)} invalid={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
