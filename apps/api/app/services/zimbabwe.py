"""Zimbabwe reference data used for public filtering."""

from __future__ import annotations

import re

PROVINCES = (
    "Bulawayo",
    "Harare",
    "Manicaland",
    "Mashonaland Central",
    "Mashonaland East",
    "Mashonaland West",
    "Masvingo",
    "Matabeleland North",
    "Matabeleland South",
    "Midlands",
)

_PROVINCE_LOOKUP = {p.lower(): p for p in PROVINCES}
_PROVINCE_PATTERN = re.compile(
    r"\b(" + "|".join(sorted((re.escape(p) for p in PROVINCES), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def normalise_province(value: str | None) -> str | None:
    """Return the canonical province name, or None when ``value`` is not a province."""
    if not value:
        return None
    return _PROVINCE_LOOKUP.get(value.strip().lower())


def detect_province(text: str | None) -> str | None:
    """A province is named in the text only if exactly one distinct province appears."""
    if not text:
        return None
    found = {_PROVINCE_LOOKUP[m.group(1).lower()] for m in _PROVINCE_PATTERN.finditer(text)}
    return next(iter(found)) if len(found) == 1 else None
