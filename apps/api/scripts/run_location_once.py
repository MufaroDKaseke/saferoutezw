"""Propose map positions for open incidents ONCE, then exit.

    cd apps/api
    python scripts/run_location_once.py                    # incidents never geolocated
    python scripts/run_location_once.py --retry-unresolved # also re-try machine-"unresolved" ones

Uses the configured geocoder (GEOCODER=geoapify needs GEOAPIFY_API_KEY). Kilometre-peg texts
such as "89-kilometre peg along the Rusape-Nyanga Road" become ESTIMATED candidates only: an
editor must pick one in the incident's Location card. Nothing is ever placed on the map
automatically from an estimate, and incidents an editor already handled are never touched.
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings  # noqa: E402
from app.core.database import get_engine  # noqa: E402
from app.jobs.logging_config import configure_logging  # noqa: E402
from app.services.geolocation import build_geocoder  # noqa: E402
from app.services.location_runner import LocationRunner  # noqa: E402
from app.services.peg_estimate import build_peg_estimator  # noqa: E402

log = logging.getLogger("run_location_once")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--retry-unresolved", action="store_true")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    provider = build_geocoder(settings)
    if provider is None:
        log.error("No geocoder is configured (set GEOCODER and its API key).")
        return 1
    runner = LocationRunner(
        get_engine(), provider, settings, args.batch_size,
        peg_estimator=build_peg_estimator(settings), retry_unresolved=args.retry_unresolved,
    )
    log.info("%s", runner.run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
