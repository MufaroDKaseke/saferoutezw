"""Run ONE RSS polling cycle now, then exit.

    cd apps/api
    python scripts/run_rss_once.py

This calls exactly the job the scheduler runs (`app.jobs.rss_poll.poll_rss_feeds`),
so what you see here is what `python -m app.jobs.scheduler` will do every cycle.

Exit code: 0 when the cycle completed (a feed that failed is recorded and logged,
not fatal); 1 when the cycle itself failed, e.g. PostgreSQL is not reachable;
130 when interrupted with Ctrl+C.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # works without `pip install -e`

from app.jobs.logging_config import configure_logging  # noqa: E402
from app.jobs.rss_poll import poll_rss_feeds  # noqa: E402

log = logging.getLogger("run_rss_once")


def main() -> int:
    configure_logging()
    try:
        poll_rss_feeds()  # logs its own summary; already logged the error if it raises
    except KeyboardInterrupt:
        log.warning("Interrupted")
        return 130
    except Exception:  # noqa: BLE001
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
