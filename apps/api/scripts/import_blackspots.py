"""Import sourced historical blackspots from a CSV file.

No blackspots are ever seeded: every row must name who published it (``source_name``),
otherwise the whole file is rejected. Rows already present (same name, source and position)
are skipped, and located incidents near new blackspots are re-matched.

CSV columns (header required):
    name, latitude, longitude, risk_level, source_name           (required)
    source_reference, description, period_start, period_end     (optional; dates are YYYY-MM-DD)

    python scripts/import_blackspots.py blackspots.csv [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from geoalchemy2 import WKTElement  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.models import Blackspot, Incident  # noqa: E402
from app.models.enums import RiskLevel  # noqa: E402
from app.services.blackspot_matching import incident_ids_near, recompute_matches  # noqa: E402

REQUIRED = ("name", "latitude", "longitude", "risk_level", "source_name")
# Zimbabwe's bounding box with a small margin: catches swapped or mistyped coordinates.
LAT_RANGE, LNG_RANGE = (-22.6, -15.5), (25.1, 33.2)


@dataclass
class Row:
    name: str
    latitude: float
    longitude: float
    risk_level: str
    source_name: str
    source_reference: str | None
    description: str | None
    start: date | None
    end: date | None


def parse_rows(lines) -> tuple[list[Row], list[str]]:
    reader = csv.DictReader(lines)
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        return [], [f"missing column(s): {', '.join(missing)}"]
    rows: list[Row] = []
    errors: list[str] = []
    for number, raw in enumerate(reader, start=2):
        try:
            values = {k: (v or "").strip() for k, v in raw.items() if k}
            for column in REQUIRED:
                if not values.get(column):
                    raise ValueError(f"{column} is required (every blackspot needs a cited source)")
            lat, lng = float(values["latitude"]), float(values["longitude"])
            if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LNG_RANGE[0] <= lng <= LNG_RANGE[1]):
                raise ValueError("coordinates are outside Zimbabwe (latitude/longitude swapped?)")
            level = values["risk_level"].lower()
            RiskLevel(level)
            start = date.fromisoformat(values["period_start"]) if values.get("period_start") else None
            end = date.fromisoformat(values["period_end"]) if values.get("period_end") else None
            if start and end and end < start:
                raise ValueError("period_end is before period_start")
            rows.append(
                Row(values["name"], lat, lng, level, values["source_name"],
                    values.get("source_reference") or None, values.get("description") or None, start, end)
            )
        except ValueError as exc:
            errors.append(f"line {number}: {exc}")
    return rows, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_file", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="validate only; change nothing")
    args = parser.parse_args(argv)

    with args.csv_file.open(newline="", encoding="utf-8-sig") as handle:
        rows, errors = parse_rows(handle)
    if errors:
        print("Nothing imported. Fix these problems first:", file=sys.stderr)
        for message in errors:
            print(f"  {message}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"{len(rows)} valid row(s); dry run, nothing imported.")
        return 0

    from app.core.database import get_engine

    radius = get_settings().blackspot_match_radius_m
    added = skipped = 0
    with Session(get_engine()) as session:
        new_ids = []
        for row in rows:
            point = WKTElement(f"POINT({row.longitude} {row.latitude})", srid=4326)
            exists = session.scalar(
                select(Blackspot.id).where(
                    func.lower(Blackspot.name) == row.name.lower(),
                    Blackspot.source_name == row.source_name,
                    func.ST_DWithin(Blackspot.geom, point, 1),
                )
            )
            if exists:
                skipped += 1
                continue
            spot = Blackspot(
                name=row.name, description=row.description, geom=point, source_name=row.source_name,
                source_reference=row.source_reference, observation_period_start=row.start,
                observation_period_end=row.end, risk_level=row.risk_level,
            )
            session.add(spot)
            session.flush()
            new_ids.append(spot.id)
            added += 1
        rematched: set = set()
        for spot_id in new_ids:
            rematched.update(incident_ids_near(session, spot_id, radius))
        for incident_id in rematched:
            incident = session.get(Incident, incident_id)
            if incident is not None:
                recompute_matches(session, incident, radius)
        session.commit()
    print(f"Imported {added} blackspot(s), skipped {skipped} duplicate(s), re-matched {len(rematched)} incident(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
