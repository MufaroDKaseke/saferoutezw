"""Best-effort privacy redaction applied before article text is stored or sent to the AI.

Removes direct identifiers of private people: phone numbers, e-mail addresses,
national ID numbers, vehicle registration plates, and the names of people described
as victims, drivers, passengers or the deceased. It is regex-based, so it is a
safeguard, not a guarantee: it errs toward redacting. Public office holders named
with their rank (e.g. police spokespeople) are intentionally left alone.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_NAME = r"[A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+){0,3}"
_NOT_PLATE = "ZRP|VID|ZBC|ZEC|ZIM|ZUM|CCC|ZIA|ZCC|ZINARA|SADC|NGO|BBC|CNN|ZTN"
_PLATE_CONTEXT = (
    r"(?i:registration number|registration|number plate|plate|reg\.? no\.?|reg\.?)[\s:]+"
)

# (kind, pattern, placeholder). A pattern with a capture group keeps the surrounding words
# and replaces only group 1; one without replaces the whole match. Order matters: the most
# specific patterns run first so they are not partly consumed by broader ones.
_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), "[EMAIL]"),
    (
        "national_id",
        re.compile(r"(?<![\w-])\d{2}[-\s]?\d{6,7}[-\s]?[A-Za-z][-\s]?\d{2}(?![\w-])"),
        "[ID NUMBER]",
    ),
    (
        "phone",
        re.compile(r"(?<![\w.])(?:\+?263|0)[\s-]?\(?\d{1,3}\)?[\s-]?\d{3}[\s-]?\d{3,4}(?![\w])"),
        "[PHONE]",
    ),
    ("plate", re.compile(_PLATE_CONTEXT + r"([A-Z]{3}\s?\d{3,4})\b"), "[PLATE]"),
    ("plate", re.compile(rf"\b(?!(?:{_NOT_PLATE})\b)([A-Z]{{3}}\s?\d{{4}})\b"), "[PLATE]"),
    # "John Moyo (34)" / "John Moyo, 34," - identified by name and age
    (
        "name",
        re.compile(rf"\b({_NAME})(?=\s*(?:\(\s*\d{{1,3}}\s*\)|,\s*\d{{1,3}}\s*,))"),
        "[NAME]",
    ),
    # "identified as John Moyo", "the deceased, John Moyo", "driver Tendai Chuma"
    (
        "name",
        re.compile(
            r"(?i:\b(?:identified as|identified him as|identified her as|named|namely|the late|"
            r"the deceased,?|deceased,?|victim,?|driver,?|passengers?,?|pedestrian,?|"
            r"conductor,?|rider,?|survivor,?))\s+(" + _NAME + ")"
        ),
        "[NAME]",
    ),
    # Courtesy titles: "Mr Moyo", "Mrs Chuma", "Sekuru Ndlovu"
    (
        "name",
        re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Mai|Baba|Amai|Sekuru|Gogo|Mbuya|Ambuya)\.?\s+({_NAME})"),
        "[NAME]",
    ),
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str | None) -> RedactionResult:
    """Return ``text`` with identifiers replaced by placeholders, plus counts per kind."""
    if not text:
        return RedactionResult("")
    counts: Counter[str] = Counter()
    for kind, pattern, placeholder in _PATTERNS:
        if pattern.groups:

            def repl(match: re.Match[str], placeholder: str = placeholder, kind: str = kind) -> str:
                counts[kind] += 1
                whole, start = match.group(0), match.start(1) - match.start(0)
                return whole[:start] + placeholder + whole[match.end(1) - match.start(0):]

            text = pattern.sub(repl, text)
        else:
            text, n = pattern.subn(placeholder, text)
            counts[kind] += n
    return RedactionResult(text, {k: v for k, v in counts.items() if v})
