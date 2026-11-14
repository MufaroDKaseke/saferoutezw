# NUST FM — AI News Monitor

`APP_MODE=nust_newsroom` turns this codebase into a general Zimbabwean **news monitor** for the NUST FM newsroom:
it collects every article from the RSS feeds, classifies and summarises each one with OpenAI, and lets journalists
search, filter and review them. Beyond monitoring, it carries a story all the way to air: a reporter takes an article,
verifies it, writes (or asks the AI to first-draft) a script, the Executive Producer approves it, it goes into a timed
bulletin, and the approved bulletin is read from a studio screen and archived (see [Story to air](#story-to-air)).
The road-safety product is still in the repository and is the default mode (`APP_MODE=road_safety`); this branch (`nust`) is
the place where the newsroom mode is developed.

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
* **Article page** — summary, topics, organisations, places, original text, review flag, retry for failed articles, and a
  **Story** card: the linked story and its stage, or *Take this story* (the Executive Producer also gets an assignee picker).
* **Stories** (`/stories`, `/stories/[id]`), **Bulletins** (`/bulletins`, `/bulletins/[id]`), **Studio** (`/studio`, `/studio/[id]`)
  and **Archive** (`/archive`, `/archive/stories/[id]`) — the story-to-air screens, described below.
* **Data Sources / Processing Activity / Settings** — the existing pages, unchanged.

Road-safety pages (`/map`, `/incidents`, `/blackspots`, `/alerts`, `/reviews`, `/intelligence`, `/public/*`) are not only hidden
from the menu: the web proxy answers them with 404, and the API does not register the matching endpoints (`/api/v1/incidents`,
`/api/v1/public/*`, `/api/v1/webhooks/*` ... all 404). The reverse holds too: the story-to-air pages (`/stories`, `/bulletins`,
`/studio`, `/archive`) and their API routes do not exist in road-safety mode.

## Story to air

Lifecycle: **article discovered → assigned → verified + script drafted → approved → on a bulletin → broadcast → archived.**
People stay in control of everything that goes on air: nothing is automatic, and the database enforces the approval rules
as well as the application.

### People and roles

| Role | Can do |
| --- | --- |
| `reporter` (new) | Take articles as stories, record verification, write and submit scripts, ask for an AI draft. Only on **their own** stories. Can **never approve** anything. Can read articles, bulletins, the studio view and the archive. |
| `editor` = **Executive Producer** | Everything a reporter can, on every story; assign stories; approve or send back scripts; build, submit, approve and broadcast bulletins. |
| `admin` | The same as the Executive Producer, plus users and settings. |
| `analyst` | Read-only everywhere (articles, stories, bulletins, studio, archive). |

The role is called **Executive Producer** everywhere in the newsroom UI. **Who is allowed to approve is one constant**:
`APPROVER_ROLES` in `apps/api/app/api/deps.py` (mirrored by `APPROVER_ROLES` in `apps/web/src/lib/newsroom/roles.ts`). Whether the
Executive Producer is also the person NUST FM wants approving is unconfirmed, so if it changes, change those two **and** the
database trigger `saferoutezw_require_human_reviewer` together.

**Self-approval is allowed but flagged.** The Executive Producer may approve a script or bulletin they wrote or submitted; it is
recorded as `self_approved` and shown with a *Self-approved* chip. A reporter can never approve their own work.

### Stories and scripts

* A story is taken from an article (`POST /stories`) or started from scratch. **One open story per article**, enforced by a
  partial unique index; a dropped or broadcast story frees the article.
* **Verification** (a note on how the facts were checked) must be recorded before a story can be submitted or an AI draft requested.
* Every save is a **new immutable script version**; older versions are never changed (database trigger). Saving carries the version
  being edited, and a stale save is refused rather than overwriting someone else's. Editing an approved story's script writes a new
  version and returns the story to *Drafting*; the approved version stays the approved one until the new one is approved.
* **Reading time** is estimated from the words at `NEWSROOM_READING_WPM` (default 150 words a minute), rounded up.
* The Executive Producer's **decision** (approve or send back with a required comment) names the exact script version they were
  looking at; if it changed meanwhile the decision is refused. Decisions are immutable and need an active human editor.
* **AI first draft** (`POST /stories/{id}/scripts/draft`) is on demand only, from a button, never automatic. It needs verification
  and a source article, sends **only the redacted article text** (never the reporter's notes) with prompt `newsroom-script-v1`
  (facts only from the article, attribute to the publisher, short spoken sentences, no invented quotes or numbers, fitted to the
  target length, article treated as untrusted data), and is saved as an *AI draft* version (model, prompt version and token counts
  kept on the row; they count in the dashboard's AI use). A person edits it; a person's edit is an ordinary version. No
  `OPENAI_API_KEY` gives a clear 503, not a crash; a failed call a 502 that changes nothing.

### Bulletins

Created ad hoc (name, air time, target length). A bulletin has **numbered revisions** (draft → pending approval → approved →
superseded, or rejected); each lists stories in order, **each pinned to one exact script version**, with an optional clip length
(replaces the reading-time estimate) and a note for the newsreader. The builder shows the running time against the target in
words and numbers, not colour alone.

* **One approved revision at a time.** Approving revision *n* runs in one transaction: the old approved revision becomes
  `superseded` and `radio_bulletins.approved_revision_id` moves to the new one, so there is never a moment with two approved
  revisions or none. The database refuses a second approved revision, a pointer to a revision without an approving decision, an
  approval without a matching decision, and any change to the items of a revision that has left draft.
* **Changes need re-approval.** An approved bulletin is never edited in place: *Change this bulletin* starts a new draft revision
  copying the approved one, which stays live (and is what the studio shows) until the new one is approved. One revision may be
  open at a time.
* **Submitting is refused** unless every item's pinned script has an approving review (and no story was dropped). A story
  rewritten after it was added is only **flagged** in the builder ("Newer script (version 2) exists"); the pinned, approved version
  is still what is read, and *Use current approved version* re-pins it.
* **Broadcast** (`POST /bulletins/{id}/broadcast`) marks the approved revision as aired once: its approved stories become
  *Broadcast* and their articles are set to **Used** (the existing review flag stays as article triage; not every article becomes a story).

### Studio view

`/studio` lists the bulletins to read; `/studio/[id]` is a read-only screen for whoever reads on air (every signed-in role can open
it). It shows only the **approved** version: version number, approval status, who approved it and when, each story's script, the
note for clips and the running time. Its status comes **only from a successful check against the server record**
(`GET /bulletins/{id}/studio`, never cached), polled every 10 seconds; no version number is remembered in the browser.

| State | Meaning |
| --- | --- |
| **Current** | The last check succeeded and nothing newer is waiting. |
| **Newer version awaiting approval** | A newer revision has been submitted; the screen still shows the approved one and says so. |
| **Cannot confirm** | Two checks in a row (about 25 seconds) failed. The script stays on screen (the reader may be mid-bulletin) with the time it was last confirmed, and the screen says it may be out of date. It recovers by itself. |

A draft still being edited is never announced to the studio.

### Archive and dashboard

`/archive` is for everyone signed in. **Stories** that went to air are searchable by title and by the headline and text of the
script that **aired** (unaired drafts are never searched or shown), by date and by category; opening one shows the aired script
and where it aired, the whole version history, the decisions behind it, and **follow-ups** (a follow-up is a story created with
`follows_story_id`; links show in both directions once both have aired; *Start a follow-up* is on the story page). **Bulletins**
lists every aired revision (a bulletin that aired twice shows both) with exactly what was read. The dashboard adds counters:
stories awaiting approval, stories in progress, bulletins awaiting approval and the next bulletin.

### Handoff

Nothing depends on WhatsApp, Word, printing or any delivery method. How NUST FM actually gets approved scripts to the newsreader
is unconfirmed, so the studio view and the approved record are the source of truth and the design is deliberately handoff-independent.

## API (`/api/v1/newsroom`)

Read: admin, editor, analyst, reporter. Write: see the roles above. Authentication and CSRF are the existing ones.

**Articles:** `GET /articles` (q, publisher_id, category, state, review_status, published_from/to, collected_from/to, sort, order, page,
page_size ≤ 100) · `GET /articles/{id}` · `PATCH /articles/{id}/review` · `POST /articles/{id}/retry` · `GET /summary` · `GET /categories`

**Stories:** `GET/POST /stories` · `GET/PATCH /stories/{id}` · `POST /stories/{id}/verify` · `/scripts` · `/scripts/draft` · `/submit` ·
`/review` · `/drop` · `GET /assignees`

**Bulletins:** `GET/POST /bulletins` · `GET /bulletins/{id}` · `POST /bulletins/{id}/revisions` ·
`PUT /bulletins/{id}/revisions/{n}/items` · `POST .../revisions/{n}/submit|approve|reject` · `POST /bulletins/{id}/broadcast` ·
`GET /bulletins/{id}/studio`

**Archive:** `GET /archive` (q, aired_from/to, category) · `GET /archive/stories/{id}` · `GET /archive/bulletins` ·
`GET /archive/bulletins/{id}/revisions/{n}`

## Configuration

| Variable | Where | Meaning |
| --- | --- | --- |
| `APP_MODE` | API `.env` | `road_safety` (default) or `nust_newsroom`. |
| `NEXT_PUBLIC_APP_MODE` | `apps/web/.env.local`, **build time** | Same switch for the web app; rebuild after changing it. |
| `NEWSROOM_MODEL` | API `.env` | OpenAI model for classification (default `OPENAI_MODEL`). |
| `NEWSROOM_PRICE_INPUT_PER_1M`, `NEWSROOM_PRICE_OUTPUT_PER_1M` | API `.env` | Optional USD prices; with both set the dashboard shows a cost estimate (classification and AI script drafts). |
| `NEWSROOM_READING_WPM` | API `.env` | Radio reading speed behind every reading-time estimate (default 150 words a minute). |
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
* Story to air (API): `test_newsroom_stories.py` (role matrix, taking an article, verification, versions, review, self-approval, the
  database guards), `test_newsroom_drafting.py` (AI drafting with a fake drafter and a fake OpenAI client, so nothing is billed),
  `test_newsroom_bulletins.py` (building, submitting, the atomic swap, broadcast, the database guards), `test_newsroom_studio.py`,
  `test_newsroom_archive.py`. Shared builders are in `tests/newsroom_helpers.py`.
* Web: `src/lib/app-mode.test.ts`, `src/components/newsroom/newsroom.test.tsx` (menu per mode, monitor, dashboard, article page),
  `story-workflow.test.tsx` (board columns, workspace, role-gated buttons, article Story card), `bulletin-workflow.test.tsx` (builder,
  time bar), `studio.test.tsx` (the polling hook and the Current / Newer pending / Cannot confirm states), `archive.test.tsx`,
  `src/lib/newsroom/newsroom-workflow.test.ts`.

## Known limits

* The feed supplies only a ~500-character excerpt; full text depends on the publisher allowing retrieval. Blocked publishers
  (NewZimbabwe, ZimLive, HarareLive, Chronicle, Manica Post) are classified from the excerpt only.
* The Reviewed / Used / Dismissed flag is article triage, not an approval; scripts and bulletins have their own approval (above).
  Nothing in newsroom mode publishes anything outside the newsroom.
* AI script drafts are drafts: they need recorded verification first and a person's edit and approval. Classifier and drafter quality
  have not been evaluated on real articles yet.
* Reporters see and edit only their own stories; the bulletin builder and approvals are the Executive Producer's. There is no
  newsreader login, audio library or recurring daily bulletin slot yet (bulletins are created ad hoc).
* A story reopened with a newer script *before* its bulletin airs stays as it is when that bulletin is marked broadcast; the archive
  keeps the version that actually aired.
* "Healthy feed" means enabled and polled successfully within about five polling cycles.
* The newsroom has no demo-data mode: it needs the API running.
* The web mode is fixed at build time; the API and the web app must be started in the same mode.
* Classifier quality has not been evaluated on real articles yet; read summaries as drafts.

## Putting it on the production server

The server holds one deployment, so deploying this branch **replaces SafeRouteZW there**: the public site, road alerts,
alert subscriptions and the WhatsApp bot stop (their API routes return 404; Meta's webhook calls will fail).

0. The deploy script takes a pre-migration database dump and runs `alembic upgrade head`, so the story-to-air tables (migrations
   `e1b3d5f7a9c2` stories and `f2c4e6a8b0d3` bulletins, which also adds the `reporter` role) arrive with it. Create reporter
   accounts afterwards (`scripts/create_user.py --role reporter`, or the admin API).
1. `infra/server/web.env` on this branch sets `NEXT_PUBLIC_APP_MODE=nust_newsroom` (baked into the web build by the deploy).
2. On the server, add `APP_MODE=nust_newsroom` to `/opt/saferoutezw/app/.env` (never committed). The scheduler and API read it on restart.
3. GitHub → Actions → *Test and deploy* → **Run workflow** → branch `nust`. (A push to `nust` does not deploy; only `main` pushes do.)
4. After it finishes: sign in at the site, then on the server queue the articles the road screen left out (optional, costs OpenAI calls):
   `cd /opt/saferoutezw/app/apps/api && sudo -u saferoute /opt/saferoutezw/venv/bin/python scripts/newsroom_requeue.py --apply`.

To go back to SafeRouteZW: remove `APP_MODE` from the server `.env` and run the workflow for branch `main`.
