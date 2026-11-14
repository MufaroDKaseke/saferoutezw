# NUST / Bulawayo version

This branch (`nust`) is SafeRouteZW scoped to **Bulawayo and the National University of Science and
Technology (NUST)**. It is the same code as `main` plus a regional mode that is **off unless configured**: with no
`SCOPE_REGION` set the application behaves exactly like the national service, and the existing tests run in both modes.

It runs beside `main` in its own folder, database (`saferoutezw_nust`), test database (`saferoutezw_nust_test`)
and ports (API 8001, web 3001). Nothing here is deployed; never merge this branch into `main`.

## What the regional mode does

| Area | Behaviour |
| --- | --- |
| Screening (`app/services/screening.py`) | With `region="bulawayo"` an item must name a place or institution from `app/data/bulawayo_places.json` (Bulawayo suburbs, roads, institutions, water dams, NUST and the towns within about 50 km) to be worth fetching. Everything else is filtered before any download or OpenAI call, with reason `no_region_connection`. |
| Civic and campus news | New primary category `city_news` (subtypes: `nust_news`, `campus_life`, `education`, `city_council`, `municipal_services`, `utilities_and_power`, `health_and_safety`, `local_events`, `other_city_news`). Any item that names a place of the region and is not sport or finance is a `city_news` candidate; civic and campus words raise the score. It is never an actionable event: it cannot create an incident or a hazard alert, and a person must still approve it. |
| Transport items | Unchanged: crashes, closures, hazards, fares and so on keep their categories, but only when they name a place of the region. A crash in Harare is filtered. |
| Extraction prompt (`app/services/extraction.py`) | `bulawayo-intel-v1`: the same strict schema and safety rules, with the regional scope and the `city_news` instructions. Version is stored on every extraction run. |
| Geography | `REGION_LAT_*`/`REGION_LNG_*` define the accepted area (editor-set points, WhatsApp pins). The Geoapify search filter becomes `rect:` instead of `countrycode:zw`. |
| Sources | `config/social_sources.yaml`: national Facebook pages are disabled; only Bulawayo pages are enabled. Trusted outlets (`TRUSTED_REGION_SOURCES`) are those whose **whole** output is local: their items may omit the place. |
| Subscriptions | `SUBSCRIPTION_PROVINCES` limits the provinces offered (Bulawayo and the two Matabeleland provinces, because alerts near Bulawayo can fall in either); bot replies say "All Bulawayo". |
| Web | `NEXT_PUBLIC_SCOPE_NAME`, `NEXT_PUBLIC_MAP_BOUNDS`, `NEXT_PUBLIC_MAP_MIN_ZOOM`, `NEXT_PUBLIC_PROVINCES` (in `apps/web/.env.local`) frame the map, wording and province pickers. The Intelligence page is in the sidebar. |

## Settings (nust `.env`)

```
SCOPE_REGION=bulawayo
SCOPE_NAME=Bulawayo
REGION_LAT_MIN=-20.8   REGION_LAT_MAX=-19.6   REGION_LNG_MIN=27.9   REGION_LNG_MAX=29.3
TRUSTED_REGION_SOURCES=Khulumani FM
SUBSCRIPTION_PROVINCES=Bulawayo,Matabeleland North,Matabeleland South
```

## Extending the place list

`app/data/bulawayo_places.json` is a **starting list**. Add suburbs, roads, schools, clinics and landmarks you know to
be in the area; leave out names that are also places elsewhere (the file explains why common words such as "Hillside"
are not included). A word match only means "mentions the region". After editing, nothing needs regenerating.

## Known limits

- The official NUST and Bulawayo City Council websites (`nust.ac.zw`, `citybyo.co.zw`) publish no RSS feed. They would
  need their own page scrapers (like the existing Bulawayo24 one) or their official Facebook Pages in the allowlist.
- Chronicle (the main Bulawayo daily) still serves an empty feed behind a Cloudflare challenge.
- Bulawayo24 and CITE carry national stories too, so they go through the same place gate as every other outlet.
- A story that never names a place of the region (for example "the council approved the tariff") is filtered unless
  its source is a trusted local outlet.
- Shona and Ndebele terms are not screened beyond "tsaona".
- The field `is_transport_relevant` keeps its historical name; in regional mode it means "relevant to this service".
