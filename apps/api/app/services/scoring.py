"""Assessments kept apart on purpose.

* credibility    - set by the pipeline from source reliability and corroboration; never changed here;
* geographic risk - from sourced historical blackspots near a *located* incident only;
* extraction confidence - lives on ``extraction_runs``;
* review priority - an ordering aid for editors.

None of these is a calibrated probability. Proximity to a blackspot never raises credibility.
"""

from __future__ import annotations

RISK_WEIGHTS = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
PRIORITY_ORDER = ["low", "normal", "high", "urgent"]
HIGH_RISK_THRESHOLD = 0.75


def geographic_risk(matches: list[tuple[str, float]], radius_m: float) -> float | None:
    """Score in [0, 1] from (risk_level, distance_m) matches, or None when nothing matched.

    The strongest nearby blackspot dominates; distance within the radius reduces it by up
    to half. "No match" is None, not 0: an incomplete dataset does not prove a road is safe.
    """
    scores = [
        RISK_WEIGHTS.get(level, 0.0) * (1 - 0.5 * min(max(distance, 0.0) / radius_m, 1.0))
        for level, distance in matches
    ]
    return round(max(scores), 3) if scores else None


def raise_priority(current: str, previous_risk: float | None, new_risk: float | None) -> str:
    """Raise review priority one step when a high-risk blackspot match first appears.

    Never lowers priority and is idempotent: it only acts when the risk crosses the threshold.
    """
    crossed = (
        new_risk is not None
        and new_risk >= HIGH_RISK_THRESHOLD
        and (previous_risk is None or previous_risk < HIGH_RISK_THRESHOLD)
    )
    if not crossed or current not in PRIORITY_ORDER:
        return current
    return PRIORITY_ORDER[min(PRIORITY_ORDER.index(current) + 1, len(PRIORITY_ORDER) - 1)]
