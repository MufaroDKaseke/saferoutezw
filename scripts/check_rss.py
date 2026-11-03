#!/usr/bin/env python3
"""Launcher for the news collector CLI (run with --help for the options).

The implementation lives in apps/api/app/ingestion/feeds.py so the API's
scheduled RSS ingestion can reuse it. This file only keeps the old command
working:

    python scripts/check_rss.py --list
    python scripts/check_rss.py --since-hours 24 --keywords accident crash

Requires: pip install -r scripts/requirements.txt
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.ingestion.feeds import main  # noqa: E402 - needs the path tweak above

if __name__ == "__main__":
    sys.exit(main())
