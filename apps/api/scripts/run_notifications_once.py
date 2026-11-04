"""Queue and deliver subscriber notifications for published alerts, ONCE, then exit.

    cd apps/api
    python scripts/run_notifications_once.py

Uses the configured notification provider (NOTIFICATION_PROVIDER=mock records messages in
memory only: nothing is sent to any phone). Safe to run repeatedly: deliveries are idempotent.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.jobs.logging_config import configure_logging  # noqa: E402
from app.services.alert_notifications import run_once  # noqa: E402

log = logging.getLogger("run_notifications_once")
LOCK_KEY = 74_201_003  # advisory lock so two runners never deliver at the same time


def main() -> int:
    configure_logging()
    settings = get_settings()
    with Session(get_engine()) as session:
        if not session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}).scalar():
            log.info("another notification run is active; exiting")
            return 0
        try:
            summary = run_once(session, settings)
        finally:
            session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            session.commit()
    log.info(
        "notifications: queued=%d sent=%d failed=%d unknown=%d skipped=%d (provider=%s)",
        summary.queued, summary.sent, summary.failed, summary.unknown, summary.skipped,
        settings.notification_provider,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
