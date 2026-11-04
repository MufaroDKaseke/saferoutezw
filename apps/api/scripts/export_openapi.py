"""Write the API's OpenAPI document to a file (default: apps/web/openapi.json).

The web app generates its TypeScript types from this file (``npm run api:types``), so
backend enums and response shapes are never copied by hand. No database is needed.

    python scripts/export_openapi.py [output.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.main import app  # noqa: E402

DEFAULT_OUTPUT = API_ROOT.parents[1] / "apps" / "web" / "openapi.json"


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    output = Path(args[0]) if args else DEFAULT_OUTPUT
    document = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    output.write_text(document, encoding="utf-8", newline="\n")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
