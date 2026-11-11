"""Queue articles that an earlier road-safety screen left out, so the newsroom pipeline classifies them.

    cd apps/api
    python scripts/newsroom_requeue.py                      # show what would be queued (changes nothing)
    python scripts/newsroom_requeue.py --apply              # queue every filtered article
    python scripts/newsroom_requeue.py --apply --status filtered,discarded --limit 200

Needs APP_MODE=nust_newsroom, so it can never be run by accident against a road-safety deployment.
Only ``processing_status`` changes (back to ``pending``); the article, its source and its history are kept,
and the previous status is noted in ``source_metadata["requeued_from"]``. Nothing is deleted.
Exit code: 0 ok; 2 not in newsroom mode.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.models import SourceItem  # noqa: E402
from app.models.enums import ProcessingStatus  # noqa: E402

ALLOWED = {ProcessingStatus.FILTERED.value, ProcessingStatus.DISCARDED.value}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", default="filtered", help="comma-separated: filtered, discarded (default: filtered)")
    parser.add_argument("--limit", type=int, default=None, help="queue at most this many, oldest first")
    parser.add_argument("--apply", action="store_true", help="make the change (default: only report)")
    args = parser.parse_args(argv)

    if not get_settings().newsroom_mode:
        print("Refusing to run: set APP_MODE=nust_newsroom (this tool is for the NUST FM newsroom only).")
        return 2
    statuses = {s.strip() for s in args.status.split(",") if s.strip()}
    unknown = statuses - ALLOWED
    if unknown:
        print(f"Unknown status: {', '.join(sorted(unknown))}. Allowed: {', '.join(sorted(ALLOWED))}.")
        return 2

    with Session(get_engine()) as db:
        counts = dict(
            db.execute(
                select(SourceItem.processing_status, func.count()).where(SourceItem.processing_status.in_(statuses)).group_by(SourceItem.processing_status)
            ).all()
        )
        print("Articles available to queue:", counts or "none")
        if not args.apply:
            print("Nothing changed. Add --apply to queue them.")
            return 0
        query = select(SourceItem).where(SourceItem.processing_status.in_(statuses)).order_by(SourceItem.received_at)
        if args.limit:
            query = query.limit(args.limit)
        queued = 0
        for item in db.scalars(query):
            item.source_metadata = {**item.source_metadata, "requeued_from": item.processing_status}
            item.processing_status = ProcessingStatus.PENDING.value
            item.screen_reason = None
            queued += 1
        db.commit()
        print(f"Queued {queued} article(s). The pipeline will classify them on its next cycle.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
