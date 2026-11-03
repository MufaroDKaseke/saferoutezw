"""Cheap keyword screen: is a headline/excerpt possibly about a road incident?

This is deliberately recall-oriented. It only decides whether an article is worth
fetching and paying the AI to read; the model and human editors decide what is
actually an incident. Whole-word matching avoids "road" firing on "broadcast".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Strong incident words: any one of these makes an article possibly relevant.
INCIDENT_TERMS = (
    "accident", "accidents", "crash", "crashed", "crashes", "collision", "collided", "collide",
    "overturned", "overturns", "rollover", "head-on", "hit-and-run", "pile-up", "run over",
    "knocked down", "plunged", "veered", "burst into flames", "caught fire", "wreckage",
    "pothole", "potholes", "black spot", "blackspot", "road carnage", "road safety",
    "road traffic", "road accident", "traffic accident",
)

# A road or vehicle setting. Needed alongside the weaker words below.
ROAD_TERMS = (
    "road", "roads", "highway", "freeway", "bridge", "intersection", "traffic", "motorist",
    "motorists", "driver", "drivers", "kombi", "kombis", "commuter omnibus", "bus", "buses",
    "haulage", "truck", "trucks", "lorry", "lorries", "vehicle", "vehicles", "minibus",
    "motorbike", "motorcycle", "bicycle", "pedestrian", "pedestrians", "zupco", "tollgate",
    "vid", "tscz", "car", "cars", "pick-up", "pickup", "haulier",
)

# Weak incident words that only count together with a road term.
WEAK_INCIDENT_TERMS = (
    "killed", "dead", "dies", "died", "death", "deaths", "fatal", "injured", "injuries",
    "burnt", "burned", "survived", "hospitalised", "hospitalized", "crushed", "smashed",
    "tragedy", "mishap", "disaster", "stranded", "flooded", "washed away",
)


def _pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(
        re.escape(t).replace(r"\ ", r"[\s-]+") for t in sorted(terms, key=len, reverse=True)
    )
    return re.compile(rf"(?<![\w])(?:{alternatives})(?![\w])", re.IGNORECASE)


_INCIDENT = _pattern(INCIDENT_TERMS)
_ROAD = _pattern(ROAD_TERMS)
_WEAK = _pattern(WEAK_INCIDENT_TERMS)


@dataclass(frozen=True)
class ScreenResult:
    relevant: bool
    matched_terms: tuple[str, ...] = ()

    @property
    def reason(self) -> str:
        if self.relevant:
            return "matched: " + ", ".join(self.matched_terms)
        return "no road-incident keywords in title/summary"


def _found(pattern: re.Pattern[str], text: str) -> list[str]:
    seen: dict[str, None] = {}
    for match in pattern.finditer(text):
        seen.setdefault(match.group(0).lower(), None)
    return list(seen)


def screen(title: str | None, summary: str | None = None) -> ScreenResult:
    """Possibly relevant when a strong incident term appears, or a weak one with a road term."""
    text = f"{title or ''}\n{summary or ''}"
    strong = _found(_INCIDENT, text)
    if strong:
        return ScreenResult(True, tuple(strong[:8]))
    road = _found(_ROAD, text)
    weak = _found(_WEAK, text)
    if road and weak:
        return ScreenResult(True, tuple((weak + road)[:8]))
    return ScreenResult(False)
