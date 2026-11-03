"""Console logging for the job commands (scheduler and one-off script)."""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Log to stdout with timestamps. Called by command-line entry points only,
    never on import, so importing the API or its tests does not touch logging."""
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s",
    )
