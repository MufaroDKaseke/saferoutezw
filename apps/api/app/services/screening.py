"""Cheap keyword screen: is a headline/excerpt possibly transport or road-safety intelligence?

Deliberately recall-oriented, deterministic and explainable. It only decides whether an
item is worth fetching and paying the AI to read. It never verifies an event and never
decides publication eligibility; the model and human editors do that. It never calls OpenAI.

Stages (see ``screen``): 1 normalise, 2 category signals, 3 Zimbabwe relevance,
4 false-positive checks, 5 score, 6 decide, 7 report.

Backward compatible: ``screen(title, summary)`` and ``ScreenResult.relevant /
.matched_terms / .reason`` behave as before; the other fields are optional additions.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.services import screening_vocab as vocab
from app.taxonomy import PrimaryCategory

_GAZETTEER = Path(__file__).resolve().parent.parent / "data" / "zimbabwe_places.json"

STRONG_WEIGHT = 3.0
CONTEXT_WEIGHT = 2.0
SUPPORT_WEIGHT = 1.0
RELEVANCE_THRESHOLD = 2.0
MAX_TERMS = 8

# Geographical relevance values (kept as plain strings for JSON/metadata storage).
GEO_ZIMBABWE = "zimbabwe"
GEO_REGIONAL = "regional"
GEO_UNKNOWN = "unknown"
GEO_FOREIGN = "foreign"

# Reason codes.
NO_SIGNAL = "no_signal"
FALSE_POSITIVE = "false_positive_context"
NO_ZIMBABWE_CONNECTION = "no_zimbabwe_connection"
NO_REGION_CONNECTION = "no_region_connection"
SUPPORT_ONLY = "support_terms_only"
MATCHED = "matched"
EMPTY = "empty"


@dataclass(frozen=True)
class ScreenResult:
    relevant: bool
    matched_terms: tuple[str, ...] = ()
    candidate_categories: tuple[str, ...] = ()
    geographical_relevance: str = GEO_UNKNOWN
    screening_score: float = 0.0
    screening_reason_code: str = NO_SIGNAL

    @property
    def reason(self) -> str:
        if self.relevant:
            return "matched: " + ", ".join(self.matched_terms)
        if self.screening_reason_code == FALSE_POSITIVE:
            return "filtered: non-transport context (" + ", ".join(self.matched_terms) + ")"
        if self.screening_reason_code == NO_ZIMBABWE_CONNECTION:
            return "filtered: no demonstrable Zimbabwe connection"
        if self.screening_reason_code == NO_REGION_CONNECTION:
            return "filtered: no connection to the monitored region"
        if self.screening_reason_code == SUPPORT_ONLY:
            return "filtered: only organisation names, no transport subject"
        return "no road-incident or transport keywords in title/summary"


# --------------------------------------------------------------------------- normalise


_TAG = re.compile(r"<[^>]+>")
_SEPARATORS = re.compile(r"[\s\-‐-―_]+")
_ORG_ALIASES = (("traffic safety council of zimbabwe", "tscz"),
                ("vehicle inspection department", "vid"))


def normalise(text: str | None) -> str:
    """Strip basic HTML, unescape entities, lower-case, treat hyphens/dashes as spaces."""
    if not text:
        return ""
    plain = html.unescape(_TAG.sub(" ", text)).lower().replace("’", "'")
    plain = _SEPARATORS.sub(" ", plain).strip()
    for long_name, short in _ORG_ALIASES:
        # An organisation's name must not count as a topic term ("Traffic Safety Council").
        plain = plain.replace(long_name, short)
    return plain


def _norm_term(term: str) -> str:
    return _SEPARATORS.sub(" ", term.lower()).strip()


def _alternation(terms: list[str]) -> tuple[re.Pattern[str], list[str]]:
    """One whole-word regex; ``m.lastgroup`` identifies which term fired."""
    ordered = sorted(dict.fromkeys(terms), key=len, reverse=True)
    parts = []
    for i, term in enumerate(ordered):
        body = r"\s+".join(re.escape(w) for w in term.split())
        suffix = "" if term.endswith("s") else r"(?:s|es)?"
        parts.append(rf"(?P<t{i}>{body}{suffix})")
    return re.compile(rf"(?<!\w)(?:{'|'.join(parts)})(?!\w)"), ordered


@dataclass(frozen=True)
class _CategoryMatcher:
    category: PrimaryCategory
    pattern: re.Pattern[str]
    terms: list[str]  # normalised term for each group index
    kinds: list[str]  # "strong" | "context" | "support"
    display: list[str]  # original spelling for reporting


def _build_matchers() -> tuple[_CategoryMatcher, ...]:
    matchers = []
    for category, entries in vocab.CATEGORY_TERMS.items():
        parsed: dict[str, tuple[str, str]] = {}
        for entry in entries:
            kind = "context"
            raw = entry
            if entry.startswith("!"):
                kind, raw = "strong", entry[1:]
            elif entry.startswith("~"):
                kind, raw = "support", entry[1:]
            parsed.setdefault(_norm_term(raw), (kind, raw))
        pattern, ordered = _alternation(list(parsed))
        matchers.append(
            _CategoryMatcher(
                category, pattern, ordered,
                [parsed[t][0] for t in ordered], [parsed[t][1] for t in ordered],
            )
        )
    return tuple(matchers)


def _phrase_regex(terms) -> re.Pattern[str]:
    pattern, _ = _alternation([_norm_term(t) for t in terms])
    return pattern


_MATCHERS = _build_matchers()


def _build_city_matcher() -> _CategoryMatcher:
    parsed: dict[str, tuple[str, str]] = {}
    for entry in vocab.CITY_NEWS_TERMS:
        kind, raw = "context", entry
        if entry.startswith("!"):
            kind, raw = "strong", entry[1:]
        elif entry.startswith("~"):
            kind, raw = "support", entry[1:]
        parsed.setdefault(_norm_term(raw), (kind, raw))
    pattern, ordered = _alternation(list(parsed))
    return _CategoryMatcher(
        PrimaryCategory.CITY_NEWS, pattern, ordered, [parsed[t][0] for t in ordered], [parsed[t][1] for t in ordered]
    )


_CITY_MATCHER = _build_city_matcher()
_ROAD = _phrase_regex(vocab.ROAD_CONTEXT)
_STAT = _phrase_regex(vocab.STAT_FRAME)
_CAMPAIGN = _phrase_regex(vocab.CAMPAIGN_FRAME)
_NEGATIVE = _phrase_regex(vocab.NEGATIVE_CONTEXT)
_REGION_NEGATIVE = _phrase_regex(vocab.NEGATIVE_CONTEXT + vocab.REGION_NEGATIVE_CONTEXT)
_LINK_CUES = _phrase_regex(vocab.ZIMBABWE_LINK_CUES)


@lru_cache(maxsize=1)
def _geo_patterns() -> tuple[re.Pattern[str], re.Pattern[str]]:
    data = json.loads(_GAZETTEER.read_text(encoding="utf-8"))
    local = [*data["provinces"], *data["towns"], *data["border_posts"], *data["roads"],
             *data["national_terms"]]
    for corridor in data["corridors"]:
        local.append(corridor)
    return _phrase_regex(local), _phrase_regex(data["foreign_terms"])


@lru_cache(maxsize=4)
def _region_pattern(region: str) -> re.Pattern[str]:
    """Whole-word regex over every place and institution of the region's reference file."""
    path = _GAZETTEER.with_name(f"{region}_places.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = [t for key, values in data.items() if not key.startswith("_") for t in values]
    return _phrase_regex(terms)


# --------------------------------------------------------------------------- stages


def _category_signals(text: str, has_road_context: bool, region_context: bool | None = None):
    """Stage 2: weighted category scores and the terms that produced them.

    ``region_context`` is None for the national service. In a regional deployment it says whether
    the text names the region; it is the "setting" that lets civic/campus terms count.
    """
    scores: dict[PrimaryCategory, float] = {}
    terms: dict[PrimaryCategory, list[str]] = {}
    strong_hit = False
    pairs = [(m, has_road_context) for m in _MATCHERS]
    if region_context is not None:
        pairs.append((_CITY_MATCHER, region_context))
    for matcher, context_ok in pairs:
        seen: dict[int, None] = {}
        # Longer terms are tried first, so "road accident" consumes "accident".
        for m in matcher.pattern.finditer(text):
            seen.setdefault(int(m.lastgroup[1:]), None)  # type: ignore[index]
        core = 0.0
        support = 0.0
        found: list[str] = []
        for idx in seen:
            kind = matcher.kinds[idx]
            if kind == "strong":
                core += STRONG_WEIGHT
                strong_hit = True
            elif kind == "context":
                if not context_ok:
                    continue
                core += CONTEXT_WEIGHT
            else:
                support += SUPPORT_WEIGHT
            found.append(matcher.display[idx])
        if core > 0:
            scores[matcher.category] = min(core + support, 6.0)
            terms[matcher.category] = found
        elif support > 0:
            scores[matcher.category] = 0.0  # support terms alone never count
            terms[matcher.category] = found
    return scores, terms, strong_hit


def _apply_frames(text: str, scores: dict[PrimaryCategory, float]) -> None:
    """Aggregate reports and campaigns are not incidents: shift weight, don't drop them."""
    road_incident = PrimaryCategory.ROAD_INCIDENT
    if _STAT.search(text) and (scores.get(road_incident, 0) > 0
                               or scores.get(PrimaryCategory.ROAD_SAFETY_DATA, 0) > 0):
        data = PrimaryCategory.ROAD_SAFETY_DATA
        scores[data] = min(scores.get(data, 0) + 2.0, 6.0)
        scores[road_incident] = max(scores.get(road_incident, 0) - 2.0, 0.0)
    if _CAMPAIGN.search(text) and (scores.get(PrimaryCategory.ROAD_SAFETY, 0) > 0
                                   or scores.get(road_incident, 0) > 0):
        safety = PrimaryCategory.ROAD_SAFETY
        scores[safety] = min(scores.get(safety, 0) + 2.0, 6.0)
        scores[road_incident] = max(scores.get(road_incident, 0) - 2.0, 0.0)


def _geography(text: str) -> str:
    local_re, foreign_re = _geo_patterns()
    local = bool(local_re.search(text)) or bool(_LINK_CUES.search(text))
    foreign = bool(foreign_re.search(text))
    if local and foreign:
        return GEO_REGIONAL
    if local:
        return GEO_ZIMBABWE
    if foreign:
        return GEO_FOREIGN
    return GEO_UNKNOWN


def screen(
    title: str | None,
    summary: str | None = None,
    *,
    region: str | None = None,
    trusted: bool = False,
) -> ScreenResult:
    """Possibly relevant when a category's evidence reaches the threshold in a Zimbabwe-
    compatible setting. Social posts pass their text as ``summary`` (or ``title``).

    ``region`` (for example ``"bulawayo"``) narrows a regional deployment: the text must name a
    place or institution of the region, and civic/campus news (``city_news``) is recognised too.
    ``trusted`` marks an outlet based in the region, whose items may name no place at all. With no
    region the behaviour is exactly the national one."""
    # Stage 1: normalise.
    text = normalise(f"{title or ''} {summary or ''}")
    if not text:
        return ScreenResult(False, screening_reason_code=EMPTY)

    # Stage 3 (needed first when a region is set): Zimbabwe relevance.
    geography = _geography(text)
    in_region = bool(_region_pattern(region).search(text)) if region else True
    region_context: bool | None = None
    if region:
        # A trusted regional outlet that names no place at all is read as local news.
        region_context = in_region or (trusted and geography == GEO_UNKNOWN)

    # Stage 2: category signals.
    has_road = bool(_ROAD.search(text))
    scores, terms, strong_hit = _category_signals(text, has_road, region_context)
    if region and in_region and scores.get(PrimaryCategory.CITY_NEWS, 0.0) < RELEVANCE_THRESHOLD:
        # General local news: naming a place of the region is itself the subject. Sport and finance
        # are still turned away by the false-positive check below.
        # A passing mention deep in a national story is not enough: the place must be in the headline
        # or be named more than once.
        pattern = _region_pattern(region)
        mentions = [m.group(0) for m in pattern.finditer(text)]
        if pattern.search(normalise(title)) or len(mentions) >= 2:
            scores[PrimaryCategory.CITY_NEWS] = CONTEXT_WEIGHT
            terms.setdefault(PrimaryCategory.CITY_NEWS, []).append(mentions[0] if mentions else region)
    _apply_frames(text, scores)
    ranked = sorted(((s, c) for c, s in scores.items() if s > 0), key=lambda x: (-x[0], x[1].value))

    # Stage 4: contextual false-positive checks.
    negative = [m.group(0) for m in (_REGION_NEGATIVE if region else _NEGATIVE).finditer(text)]
    if not ranked:
        if any(terms.get(c) for c in terms):  # only organisation names matched
            return ScreenResult(False, (), (), geography, 0.0, SUPPORT_ONLY)
        if negative:
            return ScreenResult(False, tuple(dict.fromkeys(negative))[:MAX_TERMS], (), geography,
                                0.0, FALSE_POSITIVE)
        return ScreenResult(False, (), (), geography, 0.0, NO_SIGNAL)
    if negative and not strong_hit:
        return ScreenResult(False, tuple(dict.fromkeys(negative))[:MAX_TERMS], (), geography,
                            0.0, FALSE_POSITIVE)

    # Stage 5: score. Geography nudges, it never creates relevance by itself.
    best = ranked[0][0]
    bonus = {GEO_ZIMBABWE: 1.0, GEO_REGIONAL: 0.5}.get(geography, 0.0)
    score = round(best + bonus, 2)
    categories = tuple(c.value for s, c in ranked if s >= RELEVANCE_THRESHOLD)

    # Stage 6: decide.
    if not categories:
        return ScreenResult(False, (), (), geography, score, NO_SIGNAL)
    if region and not region_context:
        return ScreenResult(False, (), categories, geography, score, NO_REGION_CONNECTION)
    if geography == GEO_FOREIGN:
        return ScreenResult(False, (), categories, geography, score, NO_ZIMBABWE_CONNECTION)

    # Stage 7: report.
    matched: list[str] = []
    for c in categories:
        for term in terms.get(PrimaryCategory(c), []):
            if term not in matched:
                matched.append(term)
    return ScreenResult(True, tuple(matched[:MAX_TERMS]), categories, geography, score, MATCHED)
