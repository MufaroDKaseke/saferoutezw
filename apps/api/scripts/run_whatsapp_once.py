"""Run one WhatsApp worker cycle by hand: process stored messages, deliver alerts, purge old data.

    cd apps/api
    python scripts/run_whatsapp_once.py

Needs WHATSAPP_ENABLED=true. Replies are only really sent when WHATSAPP_SEND_MODE=live (otherwise
they are recorded by the mock client and nothing leaves this machine).
Exit code: 0 ok; 1 the bot is disabled.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.jobs.logging_config import configure_logging  # noqa: E402
from app.jobs.whatsapp_dispatch import run_cycle  # noqa: E402


def main() -> int:
    configure_logging()
    settings = get_settings()
    if not settings.whatsapp_enabled:
        print("WHATSAPP_ENABLED is false: nothing to do.")
        return 1
    summary = run_cycle(get_engine(), settings)
    print(
        f"mode={settings.whatsapp_send_mode} processed={summary.processed} retried={summary.retried} "
        f"failed={summary.failed} alerts_queued={summary.alerts_queued} alerts_sent={summary.alerts_sent} purged={summary.purged}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
