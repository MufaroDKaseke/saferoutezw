# SafeRouteZW: answers to the five evaluation questions

**Written for:** the evaluators, who may not have seen the system before.
**Live system:** <https://saferoute.momo.co.zw> (public pages need no login: `/public/alerts`, `/public/map`, `/public/routes`).
**Prepared:** 4 November 2026, from the repository (28 commits before this document) and the working database.

## How to read this document

- Every number, timestamp, reference code and commit below was read from the repository or the database. Nothing is estimated unless it says **estimate**.
- The record counts and example IDs come from the **development database**. Check that the example records also exist on the production server before submitting. If they do not, repeat the same steps with the equivalent production record.
- Items marked **TEAM TO SUPPLY** cannot be produced from code: screenshots, evidence of conversations with real people, and vendor dashboards. Each one lists exactly what to capture.
- Two things in this brief have no honest answer yet, and this document says so rather than inventing one:
  - **Question 2:** no record of stakeholder engagement exists in the repository.
  - **Question 4:** the system has no usage or cost page.

---

## Question 1. One real media problem, shown end to end

### The problem

A road crash is reported in a sensational, off-topic frame. The headline is about something else and the road user's useful facts are buried or missing. Readers and sub-editors who skim cannot tell the place, the time or the hazard. Reports about the same crash may repeat, and may name victims.

### The real example

| Item | Value |
|---|---|
| Headline as published | "279kg of mbanje at accident scene: Kombi driver and conductor flee on foot after crashing at police roadblock" |
| Outlet | MyZimbabwe, published 6 Sep 2026 |
| Link | `https://www.myzimbabwe.co.zw/news/189946-279kg-of-mbanje-at-accident-scene-kombi-driver-and-conductor-flee-on-foot-after-crashing-at-police-roadblock.html` |
| What a reader takes away | A drug story. The road, the hazard and the time are not in the headline. |

### What the system did with it (real timestamps, UTC, 4 Nov 2026)

| Time | Step | Result |
|---|---|---|
| 05:45:53 | Collected from the outlet's RSS feed | Stored as a source item |
| (after collection) | Keyword screen on headline and summary | Passed: "matched: accident, crashed" |
| (pipeline) | Full article fetched, then redacted | 6,684 characters kept; phone numbers, IDs, plates and victim or driver names replaced with placeholders **before** the text is stored or sent to the AI |
| 05:50:31 | AI extraction (`gpt-4o-mini`, prompt `road-incident-v2`) | 2,106 tokens in, 227 out. Type `collision`, 2 vehicles, road "Harare–Masvingo Highway", occurred 2026-09-04 03:40, severity `unknown` (not guessed), confidence 0.9. Three verbatim evidence quotes kept. |
| 05:50 | Candidate incident created | Status `candidate`, credibility score 0.45 (single source, so deliberately low). It **cannot** be published from here. |
| 06:32:24 | Editor confirms the location and approves the bulletin | Location status `editor_confirmed`. Bulletin v1: **"Collision – Harare–Masvingo Highway. A kombi crashed into a parked vehicle at the 188km peg along the Harare–Masvingo Highway."** |
| 07:02:06 | Editor publishes | Alert `published`; appears on the public site |

The published text drops the drug-seizure frame and the "fled on foot" detail. It keeps what a motorist needs: what, where and which road. The system never put a point on the map from the vague text. A human confirmed the location.

### The three screenshots (TEAM TO SUPPLY)

Log in as an editor or analyst. The IDs below are from the development database. If production differs, search for "279kg" on the News Monitor page.

1. **The raw story and what the pipeline did.** Open `/news/f929e538-8571-4bc8-96a4-1a3f060c6c97` (Article detail). Capture: the original headline, the "Processing timeline", and the AI-suggested fields. Caption: "Source article and what the AI suggested. Not confirmed."
2. **The human gate.** Open `/reviews/177b1ad0-0442-4479-8c53-53d73b942c58` (Review workspace). Capture: the evidence quotes, the credibility score 0.45, the location panel showing `editor_confirmed`, and the bulletin with **Approve** and **Publish**. Caption: "Nothing is public until an editor approves this exact wording."
3. **What the public sees.** Open `/public/alerts/f58ac949-34b5-430b-8174-bbfd6457edb5`. Capture: the neutral headline and body, with no victim names. Caption: "The published notice."

### How people deal with the same story today without the system

This describes the general practice. **Confirm it with your interviewees before submitting** (see Question 2).

- An editor or reporter finds the crash by scrolling news sites and Facebook pages, or from a forwarded WhatsApp message. There is no feed that separates road crashes from the rest of the news.
- They read the full story, work out the road and time by hand, and phone the police or the outlet to check.
- They rewrite it themselves if they want to warn drivers. Every outlet repeats this work for the same crash.
- Names and personal details stay in whatever is republished unless the writer removes them.

### Where to try it

- **Public, no login:** <https://saferoute.momo.co.zw/public/alerts> shows the published notice. `/public/map` and `/public/routes` show the map and route check.
- **Staff side:** `/login`, then `/news`, `/reviews`, `/alerts`. **TEAM TO SUPPLY:** create a read-only `analyst` account for the evaluators (`python scripts/create_user.py --role analyst`) and put the email and password in the submission form. Do not commit them.

---

## Question 2. Engagement with a person who faces the problem

**Status: no evidence of stakeholder engagement exists in the repository or the database, so there is nothing true to show here yet.** Nothing in the code, commits or docs records an interview, a message or a feedback session. Inventing one would fail an evaluator's check.

### What to supply (TEAM TO SUPPLY)

For each person you spoke to (a journalist, editor, fact-checker or reader):

| Field | What to provide |
|---|---|
| Who and role | Name or a described role if they want anonymity, and their outlet |
| When and how | Date and channel (call, WhatsApp, in person, email) |
| Evidence | Screenshot of the message thread, or notes, or a short signed statement |
| What they said | One or two verbatim sentences |
| What you changed | The screen, the commit hash and the date |
| Before / after | Two screenshots of that screen |

### Dated changes that could be linked, if true

The git history gives exact dates and hashes. Link a change to a person **only if the change really came from them**.

| Commit | Date (Africa/Harare) | Change | Possible link |
|---|---|---|---|
| `29dfb52` | 4 Nov 2026 | Page descriptions cut to one short line and set in smaller text. Dashboard cards now say "social media" instead of "RSS". Transport Intelligence hidden from the menu. | Product-owner feedback. Applies if that feedback came from an editor. |
| `b587d59` | 4 Nov 2026 | AI-drafted summary for the editor to review and edit | Editor workflow |
| `f5cab6c` | 4 Nov 2026 | Editor can confirm a location rather than trust the geocoder | Editor workflow |
| `4de2944` | 4 Nov 2026 | Public site redesign (the old screens are saved in `design/public-redesign-concept/current-site-screenshots/`, the new designs in `artboards/`) | A ready-made before/after pair |

For `29dfb52`, which is the most recent change, **ask the person who requested it who they were relaying**. If it was an editor, that is your date and your quote.

---

## Question 3. Build record, what we built, what we took, what is incomplete

### The record of edits

Printed with `git log --reverse --format='%h | %ad | %an | %s' --date=short`. There are 28 commits between 3 and 4 Nov 2026, by two authors (`MufaroDKaseke`, `brito79`).

| Commit | Date | Author | Edit |
|---|---|---|---|
| `4dac854` | 3 Nov | MufaroDKaseke | Initialize monorepo foundation |
| `f68d27d` | 3 Nov | MufaroDKaseke | Next.js frontend scaffold and UI components |
| `7e2391a` | 3 Nov | brito79 | Script for extracting feeds |
| `36e5982` | 3 Nov | brito79 | Extract full article content, authors, tags, images |
| `030e65f` | 3 Nov | MufaroDKaseke | PostgreSQL/PostGIS database layer with Alembic migrations |
| `b6f363e` | 3 Nov | MufaroDKaseke | Local RSS polling scheduler |
| `5e95c2a` | 3 Nov | brito79 | RSS article pipeline: full-article fetch, redaction, OpenAI extraction |
| `5b29b12` | 4 Nov | MufaroDKaseke | Editorial dashboard frontend |
| `0314178` | 4 Nov | brito79 | Auth: server-side sessions, Argon2id, CSRF, role-based access |
| `2ffb65e` | 4 Nov | brito79 | Read-only API: dashboard, news, sources, processing, incidents |
| `55ad951` | 4 Nov | brito79 | Geolocation and blackspot intelligence |
| `f5cab6c` | 4 Nov | brito79 | Human editorial workflow: bulletin versions, decisions, location confirmation |
| `718925c` | 4 Nov | brito79 | Web app connected to the real API |
| `94ec365` | 4 Nov | brito79 | Public site, publishing, routing, subscriptions, social ingestion |
| `b587d59` | 4 Nov | brito79 | AI summary draft; dashboard fixes |
| `4de2944` | 4 Nov | MufaroDKaseke | Transport intelligence: classification, statistics, review, public pages |
| `896b470` | 4 Nov | brito79 | WhatsApp bot: report an incident, road alerts, route check |
| `36ba64b` | 4 Nov | MufaroDKaseke | Production server setup and GitHub Actions deploy |
| `110dea5` | 4 Nov | brito79 | Three more Facebook pages on the allowlist |
| `29dfb52` | 4 Nov | brito79 | Blackspots from incident clusters; OpenAI schema fix; page copy |

The 8 remaining commits are small fixes, docs, a dashboard chart and one merge. Run the git command above to print them all.

**Documentary evidence from the system itself:**
- The `audit_events` table holds 116 append-only rows.
- The `ingestion_runs` table holds 69 polling runs (8 failed).
- The `extraction_runs` table holds 159 AI calls with model, prompt version, token counts and any error message.

Print or screenshot the Processing Activity page (`/processing`) for the same period.

**Quality checks at submission:** 775 backend tests and 131 frontend tests pass. The repository holds about 17,200 lines of API code, 9,300 lines of API tests and 32,500 lines of web code (the web figure includes a generated API-types file).

### One part we built ourselves: the human-approval gate

No library provides this. It lives in the database, so an application bug cannot skip it:

- Only an active human `admin` or `editor` can record an editorial decision. The AI service account can draft but never review.
- An incident cannot become `approved` or `published` without an approving review.
- An approval names one exact bulletin version. Editing the text afterwards reopens the incident.
- Bulletin versions, reviews and audit events are append-only.
- A public alert cannot be created unless that approval still stands.

Where to look: the initial Alembic migration `20261103_1758_7ba24614c7eb_initial_saferoutezw_schema.py` (the triggers) and `apps/api/app/services/editorial.py` and `publishing.py`. The README documents the rules.

Also built by us: the privacy redaction step, the origin check that rejects social posts from the wrong account, the keyword vocabulary, and the incident-cluster blackspot logic (`apps/api/app/services/blackspot_clusters.py`, 4 Nov).

### What we took ready-made

| Need | Taken from |
|---|---|
| Language understanding | OpenAI `gpt-4o-mini`, Structured Outputs (strict JSON schema) |
| Facebook page collection | Apify Actor `neverempty/facebook-page-posts-scraper` |
| Address to coordinates | Google Geocoding API or Geoapify (a setting) |
| Route calculation | Geoapify routing |
| WhatsApp | Meta WhatsApp Business Cloud API |
| Web framework and data | FastAPI, SQLAlchemy, Alembic, PostgreSQL, PostGIS |
| Feeds and scheduling | `feedparser`, APScheduler, `beautifulsoup4` |
| Security | `argon2-cffi`, `cryptography` (Fernet), `phonenumbers` |
| Interface | Next.js, React, Tailwind, shadcn/Radix, Leaflet, Recharts, TanStack Table |
| Hosting | Ubuntu droplet, nginx, pm2, Let's Encrypt, GitHub Actions |

### One real example where it is not complete or perfect

**A foreign news story passes the keyword screen and reaches the editor queue as a Zimbabwean road incident.**

- Headline: "Nine killed as private jet plunges into Florida neighbourhood and explodes" (Nehanda Radio, 2 Nov 2026).
- The screen matched "killed" and "plunged". The AI created incident `SRZ-20261101-A951A5`: type `road_hazard`, severity `fatal`, location "Military Trail in Greenacres, Palm Beach".
- An editor rejected it on 4 Nov 2026 at 06:53 UTC with the note "not relevant".
- **The weakness is still there.** Running today's screen on that headline still returns `relevant = True`, with geography "unknown". Nothing in the keyword stage checks for a Zimbabwe link. The editor catches it, which is the design, but it costs reviewer time.
- The newer transport-intelligence prompt (`transport-intel-v1`) tells the model to mark foreign events as not relevant. **I did not run it against this story**, so we cannot yet say it would catch it.

Smaller, verified gaps:
- **AI output is sometimes unusable.** 18 of 159 recorded AI runs failed. 11 returned `occurred_time` in an invalid format and 2 returned an invalid `occurred_on`; the validator rejected them and nothing was saved. 5 were refused by the API for an unsupported setting during early testing.
- **No age check on publishing.** The alert in Question 1 was published on 4 Nov for a crash on 4 Sep, 61 days earlier. The publish path checks the bulletin version, not the age of the event.
- **The README is out of date.** It still says only the health endpoint exists.

---

## Question 4. Usage, cost and what breaks first

### The honest answer about the screenshot

**The system has no page that tracks usage or cost.** Searching the web app finds no cost or usage view. The Processing Activity page shows what the pipeline did at each stage, not what it cost. Token counts are stored per AI run in the database, but I found no screen that shows them. We cannot honestly give you a screenshot of a page that does not exist.

### Screenshots you can supply today (TEAM TO SUPPLY)

1. OpenAI dashboard, Usage page, for 3–4 Nov 2026 (the real bill).
2. Apify console, Billing and Usage, for the Facebook Actor.
3. DigitalOcean droplet graphs (CPU, memory), or `pm2 monit` over SSH.
4. `/processing` in the app, for the pipeline funnel.

If you want an in-app page, the data is already in `extraction_runs` and `ingestion_runs`. Building a small "Usage" page is a short job; ask and I will do it.

### What the data says (development database, 3 Nov 20:11 to 4 Nov 07:23 UTC)

| Measure | Value |
|---|---|
| Items collected | 5,668 (5,655 from RSS, 13 from Facebook) |
| Stopped by the free keyword screen, never sent to the AI | 5,479 (96.7%) |
| Discarded after reading, or page unreadable | 94 and 45 |
| Reached the AI and became candidate incidents | 47 |
| Reviewed by an editor | 5 (3 approved, 2 rejected) |
| Published | 1 |
| AI calls that succeeded (`gpt-4o-mini`) | 134, using 208,188 input and 24,913 output tokens |
| **Estimated** AI cost for those calls | **about $0.046** (about $0.0003 per article). This uses OpenAI's list price of $0.15 per million input tokens and $0.60 per million output tokens. **Verify the price on OpenAI's pricing page.** The OpenAI dashboard is the real figure. |
| Database size | 32 MB |

Seven further successful calls were recorded under a different model name (`gpt-6-luna`); they are left out of the cost estimate. Check them against the OpenAI dashboard.

### Which part uses the most

- **Money per item: Apify (social posts).** The Actor charges about $0.0045 per post, plus per-page and per-start fees. At the configured caps the post charges alone are at most about **$0.81 a day** (**estimate**: 24 runs a day, 6 per account, at 15/5/5/5 posts per run). OpenAI extraction costs less than that for the whole 11-hour run.
- **Server resources: the single small server.** The production host has 2 GB of RAM and 1 vCPU. The three processes are capped at 700 MB (web), 400 MB (API) and 400 MB (scheduler) before PostgreSQL and the system, with 2 GB of swap behind that. We have not measured CPU, so we cannot say which process uses the most. `pm2 monit` will show it.

### What would stop first with 10 organisations at once

In order of how soon it hurts:

1. **The system is single-tenant.** There is no organisation concept in the data model (I searched the models). Ten organisations would share one review queue, one set of sources, one set of approvers and one public feed. One organisation's editor could approve another's report. This breaks the idea before any hardware limit does.
2. **Editor time.** In the sample run, 47 candidates arrived and 5 were reviewed. The AI scales with money. The human gate scales with the number of editors.
3. **The social run cap is already exceeded with one organisation.** `SOCIAL_MAX_RUNS_PER_DAY` is 24 for all accounts together. The four allowlisted pages each poll every 120 minutes, which asks for 4 × 12 = **48 runs a day**. Half of the polls are skipped today. Ten organisations with their own pages would be starved.
4. **Memory on the 2 GB server.** Heavier use of the web app, API and scheduler on one machine is the likely first hardware failure.
5. **One API worker, and a rate limiter that lives inside that process.** It is fine at one worker. If you add workers, each keeps its own counter.

Not a first bottleneck: AI throughput. The pipeline processes 25 items every 180 seconds, which allows roughly 11,500 items a day against the 5,668 collected.

---

## Question 5. Where AI is used, and what it learns from

### Where AI is used

| # | Where | What it does | Code |
|---|---|---|---|
| 1 | Extraction | Reads one redacted article or post and returns structured JSON: relevance, category, type, severity, road, place, date and time, evidence quotes, confidence. A strict schema constrains the reply and the server validates it again. | `apps/api/app/services/extraction.py` |
| 2 | Summary draft | Drafts a 40–90 word neutral notice for an editor to edit. It never states casualty counts or names, and a second check blocks phone numbers, emails, IDs and plates. | `apps/api/app/services/summarise.py` |

The AI never approves, publishes or places a pin. Geocoding is a map service, not AI.

**The system does not train or fine-tune any model.** What it "learns from" is data the team and editors maintain, not model weights.

### The information it uses, and where it came from

| Information | Sample | Source |
|---|---|---|
| Keyword vocabulary | `"!road accident"`, `"!tsaona"` (Shona for accident), `"!kombi crash"`, `"!pothole"` | Written by the team in `screening_vocab.py` (4 Nov) |
| Prompt and categories | 9 categories, `transport-intel-v1` rules, such as "a figure like 1,800 road deaths in 2025 is a statistic, not a new accident" | `extraction.py`, `taxonomy.py` |
| Source allowlist | Four Facebook pages, including "Road Watch Zimbabwe" (`platform_account_id: 100064711207797`) | `config/social_sources.yaml` |
| News feeds | 26 configured sources | `sources` table |
| Editor decisions | 3 approvals, 2 rejections, 3 location confirmations | `editorial_reviews`, `incidents` |
| Blackspot history | **0 loaded.** Derived hotspots come from 3 or more incidents within 1 km. None exist yet in the sample data. | `blackspots`, `blackspot_clusters.py` |

### Before and after, same example

**Example: the Chivayo helicopter story** ("Makandiwa invokes Chiwenga's late wife in bitter row over Chivayo's death", Nehanda Radio).

| | Before (4 Nov 2026, 05:47 UTC) | After (current code) |
|---|---|---|
| What changed | The first keyword screen | The 4 Nov vocabulary in commit `4de2944`, which adds a non-transport context list |
| Screen result | `matched: crash` (sent onward) | `relevant = False`, reason `false_positive_context` (matched "helicopter") |
| Outcome | The AI created incident `SRZ-20190531-0F6B18`, dated 2019-05-31. An editor rejected it as "Not relevant" at 06:30. | Filtered at the free stage. No AI call, no editor time. |

**Wider effect of the same change.** I re-ran today's screen over the 5,479 items currently marked filtered, most by the earlier screen. **120 (2.2%) would now pass**, for example "Transport industry faces tighter oversight as speed monitoring system goes live" and "US$1bn targeted for road rehabilitation". Some are wrong: "Sadc moves to modernise ageing air-traffic network" matched "upgrade" as road infrastructure, and "Bulawayo Oil Plant…" matched "transport operators". The vocabulary is a tradeoff and needs tuning.

**Allowlist example (`110dea5`, 4 Nov).** Before: one Facebook page (the Zimbabwe Republic Police page). After: four. That is the only change between the two states.

### What needs updating as the information grows

1. **Re-screen old items.** Nothing re-screens items already marked `filtered`. The 120 above stay filtered until someone writes a back-fill job.
2. **Vocabulary and false-positive lists.** Add terms by hand and test them. Add a Zimbabwe-link check to the screen, since the Florida jet story still passes (see Question 3).
3. **Prompt versions.** Every run records the prompt version. Bump it with each prompt change and re-run a fixed set of past articles to compare. There is no such regression set yet.
4. **The social run cap and the allowlist.** Raise `SOCIAL_MAX_RUNS_PER_DAY` or lengthen each page's interval, or polls get skipped (Question 4).
5. **Editor capacity and a usage page.** More sources produce more candidates than the review queue can clear.
6. **Blackspots.** The cluster radius (1 km) and minimum (3 incidents) are settings. They need review when real data arrives, and the route planner does not use derived blackspots yet.
