# Transport intelligence

SafeRouteZW turns transport, traffic, accident and road-safety data into maps, visualisations,
alerts and journalism. This document describes the classification pipeline added on top of the
original incident monitoring. It does not replace the incident workflow.

## Three separate concepts

| Concept | Where it lives | Example |
| --- | --- | --- |
| Source content | `source_items` | an RSS article or a configured social post |
| Classified intelligence | `intelligence_records` (+ `statistical_observations`) | a toll-fee announcement, a fatality report |
| Actionable road event | `incidents` (existing) | a collision, a road closure |

Only a record whose `record_kind` is `actionable_event` and whose category is `road_incident`,
`traffic_disruption` or `road_hazard` can be linked to an incident. This is enforced in three
places: `app.taxonomy.may_create_incident`, the pipeline, and a database CHECK
(`only_actionable_events_link_incidents`). Policy, statistics, campaigns and infrastructure
announcements never become incidents, and publishing them never creates a hazard alert.

## Taxonomy

`apps/api/app/taxonomy.py` is the single definition: 10 primary categories with their subtypes,
record kinds, temporal statuses, geographic scopes and publication outputs. The web app uses a
generated copy, `apps/web/src/lib/taxonomy.generated.ts`:

    cd apps/api
    python scripts/export_taxonomy.py          # regenerate after editing the taxonomy
    python scripts/export_openapi.py && (cd ../web && npm run api:types)

A backend test fails if the committed web file drifts from the taxonomy.

## Pipeline

1. **Keyword screen** (`app/services/screening.py`, vocabulary in `screening_vocab.py`, place
   reference in `app/data/zimbabwe_places.json`). Deterministic; never calls OpenAI. It returns
   `candidate_categories`, `geographical_relevance`, `screening_score` and a reason code in
   addition to `relevant`, `matched_terms` and `reason`. Foreign events qualify only with a
   Zimbabwe link; a Zimbabwean publisher does not make a foreign story relevant.
2. **Fetch and redact** the full article (unchanged).
3. **One OpenAI call** (`app/services/extraction.py`, schema `app/schemas/intelligence.py`,
   prompt `transport-intel-v1`) returns the classification plus one payload block for the primary
   category and any statistical observations. Nothing in it is verified.
4. **Storage** (`app/services/intelligence.py`, `pipeline._save_extraction`): an intelligence
   record is always stored for relevant items; an incident candidate is created only when the
   taxonomy allows it.
5. **Editorial review** (`app/services/intelligence_editorial.py`): editors save immutable
   versions (correcting category, subtype, scope, date, summary and verifying each figure),
   approve the exact latest version, and then publish it as a chosen output in a separate step.
   Versions and reviews are append-only in the database.
6. **Public site**: `/api/v1/public/transport/{news,insights,statistics}` and
   `/public/transport` expose only published, verified, privacy-safe items. Hazard alerts
   (`/public/alerts`, `/public/map`) are unchanged and come only from published incidents.

## Configuration

- `INTELLIGENCE_CATEGORIES_ENABLED` (optional): comma-separated primary categories to fetch and
  classify. Empty means all. Items outside the list are filtered at screening, before any fetch
  or OpenAI cost.
- Existing OpenAI, pipeline and social settings are unchanged.

## Data rules

- Statistics keep metric, value, unit, reporting period, coverage, source, methodology and a
  preliminary flag. Figures with different periods, sources or definitions are never summed.
  Counts of classified news reports are labelled as such and are not official statistics.
- Trends report `sufficient_data=false` below 30 records and say what they count.
- Existing incidents are not reclassified or backfilled.

## Known limits

- Road segments and corridors are stored as text. There is no verified road-segment geometry, so
  infrastructure projects have no map markers and are not drawn as closures.
- Shona and Ndebele screening covers only "tsaona" (accident); other terms need verification.
- Topic linking (`topic_key`) groups follow-up coverage heuristically; editors confirm.
- The journalism insights are leads (related coverage, corridor concentrations, newly reported
  figures), not generated articles.
