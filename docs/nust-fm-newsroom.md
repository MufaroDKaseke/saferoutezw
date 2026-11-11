# NUST FM — AI News Monitor

`APP_MODE=nust_newsroom` turns this codebase into a general Zimbabwean **news monitor** for the NUST FM newsroom:
it collects every article from the RSS feeds, classifies and summarises each one with OpenAI, and lets journalists
search, filter and review them. The road-safety product is still in the repository and is the default mode
(`APP_MODE=road_safety`); this branch (`nust`) is the place where the newsroom mode is developed.

It builds on the earlier Bulawayo scope (`docs/nust-bulawayo.md`). That regional screen is not used in newsroom mode,
because newsroom mode keeps every article; its settings stay in place and are simply ignored.

## What each mode does

| | `road_safety` (default) | `nust_newsroom` |
| --- | --- | --- |
| RSS collection, dedup, source health | yes | yes (unchanged) |
| Article retrieval + redaction | yes | yes (unchanged) |
| Keyword screen decides what is kept | yes (road keywords) | **no: every article is kept** |
| OpenAI | road incident extraction | **general news classification + summary** |
| Incident candidates, geocoding, blackspots | yes | **off** |
| Road alerts, public site, route planner, subscriptions, WhatsApp bot, social polling | yes | **off (not mounted, not scheduled)** |
| Editorial incident review and publication safeguards | yes | untouched (not used) |
| Landing page | road dashboard | **News Monitor overview** |

The mode is chosen once, centrally: `Settings.app_mode` / `newsroom_mode` on the API (`app/main.py` builds the app per mode)
and `NEXT_PUBLIC_APP_MODE` on the web app (`src/lib/app-mode.ts`, `src/proxy.ts`). There are no branch-name checks anywhere.

## Pipeline in newsroom mode

1. **Collect** — the existing RSS poller stores every entry (publisher, original URL, headline, published time, collection time,
   feed excerpt, source id). Duplicates are rejected by the database as before.
2. **Keep** — personal details are redacted, then the article is kept. The only thing turned away is an entry with nothing to read
   (no headline, excerpt or link).
3. **Fetch** — the full article is retrieved. If the page cannot be read (blocked publisher, paywall, dead link) the article is
   classified **from the feed excerpt** and marked `Read from the feed excerpt only`. Nothing is invented.
4. **Classify** — one OpenAI call per article returns the structured result below. Identical text that was already classified is
   **not sent again**: the earlier classification is copied (`reused_from`). Failures are retried up to `PIPELINE_MAX_ATTEMPTS`,
   then shown as *Failed*, where an editor can press *Try again*.
5. **Review** — journalists set a flag (New / Reviewed / Used / Dismissed) and an optional note; each change is audited.

Articles are stored first and classified in later pipeline cycles (every `PIPELINE_INTERVAL_SECONDS`, `PIPELINE_BATCH_SIZE` at a
time), so classification never blocks collection.

### What the classifier returns

Primary category (and an optional secondary one) from **13 general categories** — Politics & Governance, Business & Economy,
Education, Health, Technology, Sports, Entertainment & Culture, Crime & Courts, Transport & Infrastructure, Environment &
Agriculture, Community & Local News, International News, Other / Unclassified — plus a short summary, topics, organisations and
places named in the article, geographic relevance (Bulawayo, Matabeleland, Zimbabwe-wide, International, Unclear), a *classification
clarity* score and an "needs editorial attention" flag with a reason.

* The headline, publisher and link are never produced by the model; they stay exactly as collected.
* The prompt forbids inventing facts, quotations, numbers or names, and treats the article as untrusted data.
* **Clarity is not truth.** It says how clearly the text supports the category. Nothing checks whether the article is accurate.

### Where it is stored (no migration)

`source_items.source_metadata["classification"]` (what the screens filter on) and `extraction_runs` (model, prompt version
`newsroom-v1`, token counts, full output). The review flag is `source_metadata["newsroom_review"]`. No table or column was added.

## Newsroom screens (web)

* **Dashboard** — collected (all time / today), classified today, pending classification, failures, healthy feeds, latest
  articles, categories, publishers, source health, tokens (and an estimated cost when prices are configured).
* **News Monitor** — list with search (headline, excerpt, text, AI summary) and filters: publisher, category, processing state,
  review status, collected date. Each row shows the AI summary, the original link and how the article was read.
* **Article page** — summary, topics, organisations, places, original text, review flag, retry for failed articles.
* **Data Sources / Processing Activity / Settings** — the existing pages, unchanged.

Road-safety pages (`/map`, `/incidents`, `/blackspots`, `/alerts`, `/reviews`, `/intelligence`, `/public/*`) are not only hidden
from the menu: the web proxy answers them with 404, and the API does not register the matching endpoints (`/api/v1/incidents`,
`/api/v1/public/*`, `/api/v1/webhooks/*` ... all 404).

## API (`/api/v1/newsroom`)

Read: admin, editor, analyst. Write (review flag, retry): admin, editor. Authentication and CSRF are the existing ones.

`GET /articles` (q, publisher_id, category, state, review_status, published_from/to, collected_from/to, sort, order, page,
page_size ≤ 100) · `GET /articles/{id}` · `PATCH /articles/{id}/review` · `POST /articles/{id}/retry` · `GET /summary` · `GET /categories`

## Configuration

| Variable | Where | Meaning |
| --- | --- | --- |
| `APP_MODE` | API `.env` | `road_safety` (default) or `nust_newsroom`. |
| `NEXT_PUBLIC_APP_MODE` | `apps/web/.env.local`, **build time** | Same switch for the web app; rebuild after changing it. |
| `NEWSROOM_MODEL` | API `.env` | OpenAI model for classification (default `OPENAI_MODEL`). |
| `NEWSROOM_PRICE_INPUT_PER_1M`, `NEWSROOM_PRICE_OUTPUT_PER_1M` | API `.env` | Optional USD prices; with both set the dashboard shows a cost estimate. |
| `OPENAI_API_KEY`, `PIPELINE_*`, `ARTICLE_*`, `RSS_*` | API `.env` | Existing settings, unchanged. |
| `TRUSTED_ORIGINS` | API `.env` | Add the web app's address (for example `http://localhost:3001`) or sign-in is refused. |

## Local setup (NUST FM copy)

```powershell
# 1. database (once): a separate database in the local PostgreSQL, then migrate
#    POSTGRES_DB=saferoutezw_nust in .env, then:
cd apps/api
..\..\.venv\Scripts\python -m alembic upgrade head
..\..\.venv\Scripts\python scripts\seed_rss_sources.py      # the feed list
..\..\.venv\Scripts\python scripts\create_user.py --email you@example.org --name "You" --role admin

# 2. run (three terminals)
..\..\.venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload
..\..\.venv\Scripts\python -m app.jobs.scheduler               # RSS polling + article pipeline
cd ..\web; npx next dev -p 3001                               # NEXT_PUBLIC_APP_MODE=nust_newsroom in .env.local
```

Articles collected earlier by the road-safety screen and left out of the pipeline can be queued for classification with
`python scripts/newsroom_requeue.py` (report only) and `--apply [--status filtered,discarded] [--limit N]`. It only moves them
back to *pending*; nothing is deleted.

**Cost.** One short OpenAI call per new article (about 5–20 per feed per day across 22 feeds). The pipeline sends at most
`PIPELINE_BATCH_SIZE` articles per cycle; identical text is classified once. Without `OPENAI_API_KEY` articles are collected,
kept and fetched, and wait as *Pending classification*.

## Tests

* API: `tests/test_newsroom_pipeline.py`, `test_newsroom_api.py`, `test_newsroom_schema.py` (kept articles of every kind, no incidents,
  duplicate reuse, excerpt fallback, retry, filters/search/metrics, roles, audit, 404 gating both ways). `conftest.py` pins
  `APP_MODE=road_safety`, so the entire existing suite is the SafeRouteZW-mode regression run.
* Web: `src/lib/app-mode.test.ts`, `src/components/newsroom/newsroom.test.tsx` (menu per mode, monitor, dashboard, article page).

## Known limits

* The feed supplies only a ~500-character excerpt; full text depends on the publisher allowing retrieval. Blocked publishers
  (NewZimbabwe, ZimLive, HarareLive, Chronicle, Manica Post) are classified from the excerpt only.
* The review flag is a label, not a multi-step approval workflow. It never publishes anything.
* "Healthy feed" means enabled and polled successfully within about five polling cycles.
* The newsroom has no demo-data mode: it needs the API running.
* The web mode is fixed at build time; the API and the web app must be started in the same mode.
* Classifier quality has not been evaluated on real articles yet; read summaries as drafts.

## Putting it on the production server

The server holds one deployment, so deploying this branch **replaces SafeRouteZW there**: the public site, road alerts,
alert subscriptions and the WhatsApp bot stop (their API routes return 404; Meta's webhook calls will fail).

1. `infra/server/web.env` on this branch sets `NEXT_PUBLIC_APP_MODE=nust_newsroom` (baked into the web build by the deploy).
2. On the server, add `APP_MODE=nust_newsroom` to `/opt/saferoutezw/app/.env` (never committed). The scheduler and API read it on restart.
3. GitHub → Actions → *Test and deploy* → **Run workflow** → branch `nust`. (A push to `nust` does not deploy; only `main` pushes do.)
4. After it finishes: sign in at the site, then on the server queue the articles the road screen left out (optional, costs OpenAI calls):
   `cd /opt/saferoutezw/app/apps/api && sudo -u saferoute /opt/saferoutezw/venv/bin/python scripts/newsroom_requeue.py --apply`.

To go back to SafeRouteZW: remove `APP_MODE` from the server `.env` and run the workflow for branch `main`.
