"""Run ONE social polling cycle now, then exit.

    cd apps/api
    python scripts/run_social_once.py                 # accounts that are due
    python scripts/run_social_once.py --name "Page"   # one account, ignoring its interval
    python scripts/run_social_once.py --list          # show the allowlist and its state (no Apify call)

Needs SOCIAL_INGESTION_ENABLED=true and APIFY_API_TOKEN in the root .env. Every Actor run is
billed by Apify (bounded by SOCIAL_MAX_CHARGE_USD_PER_RUN and SOCIAL_MAX_RUNS_PER_DAY).

Exit code: 0 cycle completed (per-account failures are recorded, not fatal); 1 the cycle
itself failed or the arguments were wrong; 130 interrupted.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # works without `pip install -e`

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.jobs.logging_config import configure_logging  # noqa: E402
from app.jobs.social_poll import poll_social  # noqa: E402
from app.models import SocialSource, Source  # noqa: E402

log = logging.getLogger("run_social_once")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", help="poll only this allow-listed source (ignores its interval)")
    parser.add_argument("--lookback-days", type=int, help="with --name: look this far back (backfill); the post cap still applies")
    parser.add_argument("--list", action="store_true", help="list the allowlist and exit")
    args = parser.parse_args(argv)
    configure_logging()
    settings = get_settings()
    engine = get_engine()
    try:
        with Session(engine) as db:
            rows = db.execute(
                select(Source, SocialSource).join(SocialSource, SocialSource.source_id == Source.id).order_by(Source.name)
            ).all()
        if args.list:
            for source, social in rows:
                print(f"{'ON ' if source.enabled else 'off'}  {social.platform:9} {source.name}  {social.account_url}  "
                      f"[{social.collection_status}] last_poll={social.last_polled_at}")
            if not rows:
                print("No social sources configured. Edit config/social_sources.yaml and run scripts/seed_social_sources.py")
            return 0
        if not settings.social_ingestion_enabled:
            log.error("SOCIAL_INGESTION_ENABLED is false; nothing was polled")
            return 1
        only = None
        if args.name:
            match = next((s for s, _ in rows if s.name == args.name), None)
            if match is None:
                log.error("No allow-listed social source named %r", args.name)
                return 1
            only = match.id
        poll_social(engine, settings, only=only, force=only is not None,
                    lookback_hours=args.lookback_days * 24 if args.lookback_days else None)
    except KeyboardInterrupt:
        log.warning("Interrupted")
        return 130
    except Exception:  # noqa: BLE001
        log.exception("Social poll failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
