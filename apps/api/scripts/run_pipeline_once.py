"""Run ONE article-pipeline cycle now, then exit.

    cd apps/api
    python scripts/run_pipeline_once.py

Runs exactly the job the scheduler runs (`app.jobs.pipeline_job.run_pipeline`):
screen new RSS items, fetch and redact the full articles, and - when OPENAI_API_KEY
is set - extract candidate incidents. Run `scripts/run_rss_once.py` first to have
items to process.

Exit code: 0 when the cycle completed (items that failed are recorded, not fatal);
1 when the cycle itself failed, e.g. PostgreSQL is not reachable; 130 on Ctrl+C.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # works without `pip install -e`

from app.jobs.logging_config import configure_logging  # noqa: E402
from app.jobs.pipeline_job import run_pipeline  # noqa: E402

log = logging.getLogger("run_pipeline_once")


def main() -> int:
    configure_logging()
    try:
        run_pipeline()  # logs its own summary; already logged the error if it raises
    except KeyboardInterrupt:
        log.warning("Interrupted")
        return 130
    except Exception:  # noqa: BLE001
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
