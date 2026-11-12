# NUST FM: story-to-air workflow (stories, scripts, bulletins, studio view, archive)

## Context

The newsroom mode (`APP_MODE=nust_newsroom`) stops at "an article, an AI summary, a Reviewed/Used/Dismissed label". NUST FM is a radio station: the real job is turning an article into a script an editor approves, placing it in a timed bulletin, getting the approved bulletin in front of whoever reads on air, and archiving it. This adds that path while keeping people in control of everything that goes on air.

Users: an Executive Producer (the manager) and reporters. Small team, so roles stay simple.

Lifecycle: Article discovered -> Assigned -> Verified + script drafted -> Approved -> On a bulletin -> Broadcast -> Archived

### Agreed requirements (core, regardless of how NUST FM currently hands scripts over)

- **One approved bulletin at a time per bulletin.**
- **Changes need re-approval.** Editing after approval creates a new revision; the approved one stays live until the new one is approved, then the swap is atomic.
- **Version visibility.** The studio view shows version number, approval status and last approval time.
- **Handoff-independent.** Nothing depends on WhatsApp, Word, printing or any delivery method.
- **Title is "Executive Producer" everywhere in the UI.** Whether the EP is also the person authorised to approve is unconfirmed, so "who may approve" lives in one constant.
- **The studio status comes from a successful check against the server record**, never a locally cached version number. If the check fails the screen says it cannot confirm.

### Decisions made with the user

- New `reporter` role (migration widens the users role check). `editor` is labelled Executive Producer in the newsroom.
- **Self-approval allowed but flagged.** Reporters can never approve their own work; the EP can approve their own, recorded as `self_approved`.
- Bulletins are created ad hoc (name, air time, target length). Recurring daily slots are a later add-on.
- First release = full path to air (stories, scripts, approval, bulletins, studio view). Archive follows straight after.
- No audio library, no newsreader login, no separate assignment page.

### My calls (check these)

- AI script drafting is **on demand only** (a button), never automatic, and requires the reporter to record verification first (a note on how it was checked). Output is stored as an AI draft; a person edits it.
- Reading-time estimate uses 150 words per minute, setting `NEWSROOM_READING_WPM`. Each bulletin item can override its duration (for a clip).
- The existing Reviewed/Used/Dismissed article flag stays (it is article triage; not every article becomes a story). A story's broadcast sets the article to `used`; the article page shows its story and stage.
- Studio view polls the server every 10 s; two failed checks (about 25 s) show "Cannot confirm".
- Any signed-in role can open the studio view (reporters or the EP may be the one reading). Analyst stays read-only.
- Archive = broadcast stories and aired bulletin revisions, searchable, with follow-up links between stories.

## Data model (one migration after `d0f2a4c6e8b3`)

Prefix `radio_` / `story_` so nothing collides with the road-safety `bulletin_versions` / `editorial_reviews`.

| Table | Purpose | Notes |
|---|---|---|
| `users.role` check | add `reporter` | widen `ck_users_role_valid` (pattern: `e5a7b3c9d1f2`) |
| `stories` | one story, optionally from an article | `source_item_id` (nullable FK), `title`, `stage` (assigned, drafting, in_review, changes_requested, approved, broadcast, dropped), `assignee_id`, `deadline_at`, `verification_note` / `verified_at` / `verified_by`, `follows_story_id`. Partial unique index: one open story per article |
| `story_scripts` | immutable script versions | `version_number`, `headline`, `body`, `estimated_seconds`, `origin` (human / ai_draft), AI `model_name`, `prompt_version`, token counts, `created_by`. Append-only trigger |
| `story_reviews` | approve / send back decisions, immutable | `reviewer_id`, `script_id` pinned to one version, `decision`, `comment`, `self_approved` |
| `radio_bulletins` | the bulletin (name, `scheduled_for`, `target_seconds`) | `approved_revision_id` pointer = the single current approved revision (a single column cannot hold two) |
| `radio_bulletin_revisions` | numbered revisions | state draft / pending_approval / approved / superseded / rejected; submitted and approved by/at |
| `radio_bulletin_items` | ordered stories in a revision | `position`, `story_id`, `script_id` (the exact approved version), duration override, text note for clips |
| `radio_bulletin_decisions` | approve / reject, immutable | `reviewer_id`, `self_approved`, `comment` |

Database guards copied from the road-safety design, not just application checks:

- Reuse `saferoutezw_forbid_modification()` (generic append-only) for `story_scripts`, `story_reviews`, `radio_bulletin_decisions`.
- Reuse `saferoutezw_require_human_reviewer()` (it reads `NEW.reviewer_id`, allows only active admin/editor) on `story_reviews` and `radio_bulletin_decisions`.
- A trigger so `approved_revision_id` can only move to a revision that has an approved decision, and items of a non-draft revision cannot change.
- AI metadata lives on `story_scripts` (not `extraction_runs`, whose `source_item_id` is NOT NULL and stories may not have an article). The dashboard token/cost query in `repositories/newsroom.py` (summary) adds these rows.

## API (new routers mounted only in newsroom mode)

Add `newsroom_stories.py` and `newsroom_bulletins.py` under `apps/api/app/api/v1/`, register them in the newsroom tuple in `app/main.py:70`. Schemas in `schemas/newsroom_workflow.py`, queries in `repositories/newsroom_workflow.py`, state rules in `services/newsroom_workflow.py`. Every change calls `record_audit` (`services/audit.py`), ids and state only.

Permissions (`app/api/deps.py`): add `NEWSROOM_READ_ROLES` (admin, editor, analyst, reporter), `STORY_WRITE_ROLES` (admin, editor, reporter), `APPROVER_ROLES` (admin, editor: the one constant to change later). Switch the existing newsroom routes from `Reader` to the new reader dependency so reporters can read articles. This router is only mounted in newsroom mode, so road-safety behaviour is unchanged.

**Stories:** `POST/GET /stories`, `GET/PATCH /stories/{id}`, `POST /stories/{id}/verify`, `/scripts` (new version), `/scripts/draft` (AI), `/submit`, `/review`, `/drop`. Reporters act only on their own stories; the EP on all. Editing a script of an approved story creates a new version and returns the story to drafting.

**Bulletins:** `GET/POST /bulletins`, `GET /bulletins/{id}`, `POST .../revisions` (copies the approved one), `PUT .../revisions/{n}/items`, `.../submit`, `.../approve`, `.../reject`, `POST .../broadcast`. Approving a revision runs in one transaction: old approved revision becomes `superseded`, `approved_revision_id` moves to the new one. Submitting is refused unless every item's pinned script is approved. If a story gets a newer script after being added, the builder flags it.

**`GET /bulletins/{id}/studio`:** the lightweight authoritative check (version, approved at/by, items with script text, total seconds, `newer_revision_pending`, `server_time`). Open to every signed-in newsroom role.

**`GET /archive`** (q, dates, category): broadcast stories and aired revisions. Follow-ups via `follows_story_id`.

**AI drafting:** new `services/newsroom_script.py`, a sibling of `NewsroomExtractor` (`services/newsroom_extraction.py`). Reuse `complete_structured`, `build_user_message`, `ExtractorUnavailable`, `from_settings`. Prompt `newsroom-script-v1`: facts only from the supplied (already redacted) article, attribute to the publisher, short spoken sentences, no invented quotes or numbers, length fitted to the target. Same untrusted-article rule as the classifier. Missing `OPENAI_API_KEY` returns a clear 503, not a crash.

New settings in `core/config.py`: `NEWSROOM_READING_WPM` (default 150).

## Web (`apps/web`)

Before writing any web code, read the Next.js guides in `apps/web/node_modules/next/dist/docs/01-app/` (layouts-and-pages, server-and-client-components, fetching-data, proxy). `AGENTS.md` says this Next version differs from what I know.

Follow the existing newsroom pattern: thin `page.tsx` in `src/app/(dashboard)/...`, a component in `src/components/newsroom/`, hand-written types in `src/lib/newsroom/types.ts`, calls in `src/lib/api/newsroom.ts` via `apiRequest`, `useResource` for fetching, shared `PageHeader`, `SectionCard`, states, status chips.

| Route | Component | Who |
|---|---|---|
| `/stories` | story board: columns by stage, card shows reporter + deadline; EP approval queue is a filter | reporters see theirs, EP all |
| `/stories/[id]` | workspace: source article beside script editor, AI draft button, verification note, reading time, submit; EP approve / send back with comment | reporter, EP |
| `/bulletins`, `/bulletins/[id]` | builder: pick approved scripts, order, running time vs target, draft -> pending -> approved, new revision | EP |
| `/studio`, `/studio/[id]` | read-only studio view with version, approval time, 10 s check and the "cannot confirm" state | everyone |
| `/archive` | search broadcast scripts and bulletins, version history, follow-ups | everyone |

- Add the new items to `NEWSROOM_NAV_GROUPS` in `components/layout/nav-config.ts`.
- Add `reporter` to `UserRole` (`types/common.ts`), `ROLE_TITLES` (`lib/api/auth.ts`; show `editor` as "Executive Producer" in newsroom mode) and the roles table in `components/settings/settings-view.tsx`. Regenerate `openapi.json` / `schema.d.ts` for the role enum (`npm run api:types`).
- Article page (`newsroom-article-detail.tsx`): a "Story" card: shows the linked story and stage, or a "Take this story" button (EP also gets an assignee picker).
- Studio view: a small polling hook (`setInterval` + `AbortController`) tracking last confirmed time. States: Current, Newer version awaiting approval (still showing approved one), Cannot confirm.

## Build order (each step ships on its own)

0. After approval: save this design to `docs/superpowers/specs/2026-11-12-newsroom-story-to-air-design.md`, add `.superpowers/` to `.gitignore` (the brainstorm mockups are in `.superpowers/brainstorm/`).
1. **Foundation:** `reporter` role + story tables migration, permissions, story API and tests.
2. **Stories on the web:** board, workspace, article "Take this story", AI script draft (with fake drafter in tests).
3. **Bulletins:** tables, API, single-approved invariant, builder page.
4. **Studio view:** studio endpoint and page with polling. This completes the first release (steps 1-4).
5. **Archive and follow-ups**, dashboard counters (stories awaiting approval, next bulletin), update `docs/nust-fm-newsroom.md`.

## Verification

**API** (needs the test Postgres; `conftest.py` runs real Alembic migrations): from `apps/api`, `..\..\.venv\Scripts\python -m pytest tests/test_newsroom_*.py`, then the full suite (it runs in road-safety mode, so it is the regression run). New tests use the `newsroom_client` fixture and a fake script drafter in `tests/newsroom_helpers.py`. They must cover:

- role matrix: reporter cannot approve; reporter cannot touch another reporter's story; analyst read-only;
- self-approval is allowed for the EP and flagged;
- editing after approval returns the story to drafting;
- append-only triggers reject UPDATE/DELETE on scripts, reviews and decisions;
- approving revision 2 atomically supersedes revision 1, and two approved revisions are impossible;
- submit refused with an unapproved or changed script;
- studio endpoint reports a newer pending revision and a stale version;
- reading-time maths; AI draft refused without verification or without a key;
- audit events written; new routes 404 in road-safety mode.

**Web:** `cd apps/web; npm test`, `npm run typecheck`, `npm run lint`. New vitest cases for nav per mode, studio-view states (current / newer pending / cannot confirm), board columns, builder time bar, role-gated buttons.

**Manual end to end** (API on :8001 with `APP_MODE=nust_newsroom`, web on :3001): as a reporter take an article, verify, draft, edit, submit. As the EP send it back, approve, build a 5:00 bulletin, approve it, open the studio view in a second window, edit the bulletin and confirm the studio keeps v1 until v2 is approved, then stop the API and confirm "Cannot confirm" appears.

**Deploy** (existing workflow, manual run for branch `nust`): the deploy script takes a pre-migration database dump and runs `alembic upgrade head`, so the new tables arrive with it. Remember this replaces SafeRouteZW on the server (see `docs/nust-fm-newsroom.md`).

## Risks / open points

- How NUST FM actually gets scripts to the newsreader is unconfirmed; this is deliberately handoff-independent. Ask the EP the five questions from the research notes before polishing the studio view.
- Who is authorised to approve (EP or someone else) is unconfirmed; one constant (`APPROVER_ROLES`) plus the database reviewer trigger must change together.
- Classifier quality is still unevaluated, so AI script drafts are drafts: verification is required before drafting, and the UI labels them "AI draft".
