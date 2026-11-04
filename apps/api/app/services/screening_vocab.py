"""Vocabulary for the keyword screen, as plain data.

Term prefixes set how a term counts:
  ``!term``  strong, self-sufficient evidence for the category (weight 3)
  ``term``   contextual: counts (weight 2) only when a road/vehicle word is also present
  ``~term``  support only (weight 1): never relevant on its own (e.g. bare organisation names)

Hyphens and spaces are interchangeable, plurals ('s'/'es') are matched automatically, and
all matching is whole-word. Keep this list deterministic and explainable; do not turn it into
a second classifier.
"""

from __future__ import annotations

from app.taxonomy import PrimaryCategory as C

CATEGORY_TERMS: dict[C, tuple[str, ...]] = {
    C.ROAD_INCIDENT: (
        "!road accident", "!traffic accident", "!head-on collision", "!head-on", "!rear-end collision",
        "!hit-and-run", "!pile-up", "!road carnage", "!tsaona", "!bus crash", "!truck crash",
        "!kombi crash", "!kombi accident", "!combi accident", "!pedestrian collision",
        "!vehicle fire", "!road crash", "!road traffic accident", "!multi-vehicle collision",
        "accident", "crash", "crashed", "crashes", "collision", "collided", "collide",
        "overturned", "overturns", "overturn", "rollover", "rolled over", "knocked down",
        "run over", "plunged", "veered", "burst into flames", "caught fire", "wreckage",
        "killed", "dead", "dies", "died", "death", "deaths", "fatal", "injured", "injuries",
        "burnt", "burned", "survived", "hospitalised", "hospitalized", "crushed", "smashed",
        "tragedy", "mishap", "disaster", "stranded",
    ),
    C.TRAFFIC_DISRUPTION: (
        "!traffic jam", "!traffic delay", "!gridlock", "!road closed", "!road closure",
        "!lane closure", "!road blockage", "!traffic disruption", "!border delay", "!border queue",
        "!tollgate congestion", "!toll gate congestion", "!traffic management",
        "!traffic restriction", "!impassable road",
        "congestion", "congested", "diversion", "diversions", "closed to traffic",
    ),
    C.ROAD_HAZARD: (
        "!pothole", "!road damage", "!road surface damage", "!flooded road", "!bridge damage",
        "!damaged bridge", "!bridge collapse", "!black spot", "!blackspot",
        "washed away", "flooding", "flooded", "floods", "debris", "landslide", "rockfall",
        "fallen tree", "impassable", "roadworks", "road works", "poor visibility", "sinkhole",
    ),
    C.ROAD_INFRASTRUCTURE: (
        "!road construction", "!road rehabilitation", "!highway upgrade", "!bridge rehabilitation",
        "!road network", "!infrastructure funding", "!new tollgate", "!new toll gate",
        "!road resurfacing", "!road project", "!road expansion", "!transport infrastructure",
        "!road maintenance", "!roads infrastructure", "!dualisation", "!bridge construction",
        "roadworks", "rehabilitation", "resurfacing", "upgrade", "contractor",
    ),
    C.PUBLIC_TRANSPORT: (
        "!public transport", "!transport operators", "!commuter omnibus", "!bus fare",
        "!transport fare", "!passenger transport", "!bus operators", "!route change",
        "!transport regulation", "!bus terminus", "!kombi fare", "!combi fare", "!rank marshals",
        "kombi", "kombis", "combi", "zupco", "service disruption", "fares", "fare", "commuters",
        "omnibus", "bus rank",
    ),
    C.FREIGHT_AND_LOGISTICS: (
        "!freight", "!haulage", "!truck queue", "!truck delay", "!cross-border transport",
        "!freight restriction", "!haulage operators", "!commercial vehicle", "!beitbridge border",
        "!chirundu border", "!border post", "!cross-border trucks", "!haulier",
        "logistics", "truckers", "trucks",
    ),
    C.ROAD_SAFETY: (
        "!road safety", "!traffic safety", "!drunk driving", "!drink driving", "!drunk-driving",
        "!vehicle roadworthiness", "!roadworthy", "!road worthy", "!vehicle inspection",
        "!driver licensing", "!driver's licence", "!driving licence", "!traffic enforcement",
        "!traffic police", "!road safety campaign", "!accident prevention", "!road fatalities",
        "!speed limit", "!speed trap", "!roadblock",
        "speeding", "overspeeding", "reckless driving", "licensing",
        "~zrp", "~tscz", "~vid", "~vehicle inspection department",
    ),
    C.ROAD_SAFETY_DATA: (
        "!accident statistics", "!road accident figures", "!road deaths", "!traffic fatalities",
        "!accident blackspots", "!traffic volumes", "!annual road safety report",
        "!crash statistics", "!accident trends", "!traffic data", "!transport statistics",
        "!safety research", "!road accident statistics", "!fatality statistics",
        "!accident figures", "!road traffic statistics",
        "fatality rate", "statistics", "statistical",
    ),
    C.TRANSPORT_POLICY: (
        "!transport policy", "!road regulations", "!toll fees", "!toll tariffs", "!toll fee",
        "!toll tariff", "!transport budget", "!vehicle regulations", "!traffic laws",
        "!transport legislation", "!road fund", "!licensing requirements",
        "toll", "tolls", "tariffs", "regulations", "legislation", "statutory instrument",
        "~zinara", "~ministry of transport", "~department of roads",
    ),
}

# A road or vehicle setting. Needed alongside every contextual (unprefixed) term.
ROAD_CONTEXT: tuple[str, ...] = (
    "road", "roads", "highway", "freeway", "bridge", "intersection", "traffic", "motorist",
    "motorists", "driver", "drivers", "kombi", "kombis", "combi", "commuter omnibus", "bus",
    "buses", "haulage", "truck", "trucks", "lorry", "lorries", "vehicle", "vehicles", "minibus",
    "motorbike", "motorcycle", "bicycle", "pedestrian", "pedestrians", "zupco", "tollgate",
    "toll gate", "vid", "tscz", "car", "cars", "pick-up", "pickup", "haulier", "tarred",
    "tollgates", "highways", "motorway", "bypass",
)

# Statistical framing: demotes the "road_incident" reading of an aggregate report.
STAT_FRAME: tuple[str, ...] = (
    "statistics", "statistical", "figures", "annual report", "trends", "fatality rate",
    "data shows", "data show", "year on year", "compared to last year", "compared with",
    "first half", "first quarter", "second quarter", "third quarter", "fourth quarter",
)

# Campaign framing: a safety campaign is informational content, not an incident.
CAMPAIGN_FRAME: tuple[str, ...] = (
    "campaign", "awareness", "clampdown", "blitz", "initiative", "programme", "program",
    "launches", "launched", "sensitisation", "sensitization",
)

# Non-transport senses of otherwise road-like words. Only rejects when no strong term fired.
NEGATIVE_CONTEXT: tuple[str, ...] = (
    "stock exchange", "stock market", "share price", "software", "server", "website", "cyber",
    "aircraft", "aeroplane", "airplane", "airline", "helicopter", "plane crash", "cricket",
    "football", "rugby", "soccer", "currency", "forex", "financial market", "market congestion",
    "bond market", "investors", "tournament", "box office", "album",
)

# Foreign events become relevant only with one of these (besides the gazetteer's Zimbabwe terms).
ZIMBABWE_LINK_CUES: tuple[str, ...] = (
    "zimbabwean", "zimbabwe registered", "zimbabwe-registered", "zimbabwe bound", "beitbridge",
    "chirundu", "plumtree", "forbes border", "nyamapanda", "north south corridor",
)
