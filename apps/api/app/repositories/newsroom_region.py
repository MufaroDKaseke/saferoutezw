"""Read-only regional matching for the newsroom article query; never an ingestion gate.

AI geography is primary. Missing, unclear and national labels can also match a
controlled regional reference in existing redacted text or named entities. An
explicit international classification is not overridden by a keyword hit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql.elements import ColumnElement

from app.models import SourceItem

_DATA = Path(__file__).resolve().parent.parent / "data"


def _read(name: str) -> dict:
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


def _phrases(terms: list[str]) -> str:
    # PostgreSQL ARE word boundaries prevent NUST matching "nustlike", etc.
    # Accept spaces, underscores and typographic hyphens between phrase words.
    phrases = [
        r"[\s_‐‑‒–—-]+".join(re.escape(word) for word in term.split())
        for term in sorted(set(terms), key=len, reverse=True)
    ]
    return r"\m(?:" + "|".join(phrases) + r")\M"


_BULAWAYO = _read("bulawayo_places.json")
_REGION = _read("newsroom_region.json")
_AMBIGUOUS = set(_REGION["ambiguous_terms"])
_PLACE_TERMS = [
    term
    for key in ("region_terms", "suburbs", "towns_and_districts", "institutions_and_places")
    for term in _BULAWAYO[key]
    if term not in _AMBIGUOUS
]
_PLACE_TERMS += [term for key in ("region_aliases", "matabeleland_north", "matabeleland_south") for term in _REGION[key]]
_PLACES = _phrases(_PLACE_TERMS)
_CAMPUS = _phrases(_BULAWAYO["nust"])
_FOREIGN = _phrases(_read("zimbabwe_places.json")["foreign_terms"])
_ZIMBABWE = _phrases(["Zimbabwe", "Zimbabwean", "Zimbabweans"])


def _entities_text(values):
    # Read actual array strings, not their JSON serialization (where newlines
    # and tabs become backslash escapes). Legacy null/scalar values are ignored.
    array = case((func.jsonb_typeof(values) == "array", values), else_=literal([], type_=JSONB))
    entries = func.jsonb_array_elements_text(array).table_valued("value")
    return select(func.string_agg(entries.c.value, " ")).scalar_subquery()


def regional_articles() -> ColumnElement[bool]:
    classification = SourceItem.source_metadata["classification"]
    geography = classification["geographic_relevance"].as_string()
    text = func.concat_ws(
        " ",
        SourceItem.title_redacted,
        SourceItem.excerpt_redacted,
        SourceItem.article_text_redacted,
        _entities_text(classification["places"]),
        _entities_text(classification["organisations"]),
    )
    # NUST is an ambiguous abbreviation. A campus-only hit with explicitly
    # foreign context needs a Zimbabwe reference; a clear regional place stands
    # on its own. Publisher names and URLs are deliberately not searched.
    campus = and_(
        text.bool_op("~*")(_CAMPUS),
        or_(~text.bool_op("~*")(_FOREIGN), text.bool_op("~*")(_ZIMBABWE)),
    )
    fallback = and_(
        func.coalesce(geography, "").in_(("", "unclear", "zimbabwe_wide")),
        or_(text.bool_op("~*")(_PLACES), campus),
    )
    return or_(geography.in_(("bulawayo", "matabeleland")), fallback)
