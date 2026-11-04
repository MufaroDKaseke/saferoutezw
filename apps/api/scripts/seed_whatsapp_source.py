"""Create the ``whatsapp`` source that owns public reports (idempotent).

    cd apps/api
    python scripts/seed_whatsapp_source.py

The bot also creates this row the first time a report is confirmed, so running this is optional;
it is useful to see the source in the editor's list before any report arrives. The source is
``unverified`` and its reports can only become candidate incidents for human review.
Exit code: 0 ok.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.database import get_engine  # noqa: E402
from app.services.whatsapp.incident_intake import ensure_source  # noqa: E402


def main() -> int:
    with Session(get_engine()) as db:
        source = ensure_source(db)
        db.commit()
        print(f"source '{source.name}' kind={source.kind} tier={source.verification_tier} enabled={source.enabled}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
