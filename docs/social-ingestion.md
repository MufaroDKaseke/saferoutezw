# Social media ingestion (Apify)

SafeRouteZW can collect new posts from **specific public accounts that an administrator has
allow-listed**, and feed them into the same pipeline as RSS articles. It never searches,
follows hashtags, discovers accounts, reads comments or follows reshares into other accounts.

| Platform | Status | Actor |
|---|---|---|
| Facebook Pages | **implemented** | `neverempty/facebook-page-posts-scraper` |
| X | not available | no verified Actor chosen |
| TikTok | not available | no verified Actor chosen |

## How it fits

```text
config/social_sources.yaml ──seed──► sources (kind=social) + social_sources
                                          │  (allowlist, interval, cursor, status)
scheduler ─► every SOCIAL_POLL_CHECK_SECONDS: which accounts are due?
                                          │
              Apify Actor, ONE account per run (capped rows, spend, time)
                                          │
              platform adapter: confirm origin of every post
                 ├─ confirmed ───────────► source_items (pending)  ─┐
                 ├─ other account ───────► dropped, counted         │  shared pipeline, unchanged:
                 └─ cannot confirm ──────► social_quarantine        │  screen ► redact ► OpenAI ►
                                                                    │  candidate incident ► editor
RSS feeds ────────────────────────────────► source_items (pending) ─┘
```

Code: `app/ingestion/normalized.py` (the `NormalizedReport` contract), `app/ingestion/social/`
(`facebook.py` adapter, `poller.py`, `runner.py` is the only module that talks to Apify,
`seed.py`), `app/jobs/social_poll.py`. `app/services/pipeline.py` knows nothing about Apify; it
only recognises `source_metadata.content_kind == "social_post"`.

> The repository had no `NormalizedReport` before this work: RSS wrote `source_items` rows
> directly. `NormalizedReport` is the explicit version of that contract. RSS was deliberately
> left on its own row builder.

## Using it

1. Put the token and switch in the root `.env` (never commit them):
   ```
   APIFY_API_TOKEN=...
   SOCIAL_INGESTION_ENABLED=true
   ```
2. Add the account to `config/social_sources.yaml` (see the comments in that file). **Verify the
   Page address yourself**; the shipped file lists none. Keep `enabled: false` until you have.
3. Apply migrations (`alembic upgrade head`), then sync the allowlist:
   `python scripts/seed_social_sources.py` (`--dry-run` validates only).
4. Try one poll: `python scripts/run_social_once.py --name "<name>"` (or `--list`).
5. Run `python -m app.jobs.scheduler`; it adds the social job automatically when both
   `SOCIAL_INGESTION_ENABLED` and `APIFY_API_TOKEN` are set.

Syncing updates configuration only. Collection state (cursor, last poll, status) is kept.
Accounts missing from the file stay as they are in the database; disable them by setting
`enabled: false` in the file.

## What is checked before a post is accepted

For every returned post, the Facebook adapter requires:

* a `postId` and a Facebook `url` (otherwise: quarantine);
* **origin**: `pageId` equals the configured `platform_account_id` when known, otherwise `pageUrl`
  must be the same Page as `account_url`. `facebookUrl` is *not* used: it is the address we asked
  for, echoed back. Another Page, or a different `pageId` → **rejected**; origin that cannot be
  confirmed → **quarantined**, never assumed;
* the post's own URL must not belong to a different account (quarantine);
* group posts are rejected; posts without text are ignored;
* the source must still be enabled at the moment of saving.

The numeric Page id is pinned from the first post whose Page address matches the configured URL;
from then on the id is authoritative. Changing `account_url` clears it.

Quarantined rows keep only a small summary (reason, post id/URL, claimed page id/name/URL),
never the post text. Engagement numbers and media are not stored. A reshare keeps its
`shared_post_url` for reference but is not followed.

## Cost controls

Every poll is a paid Actor run (about $0.0045 per post plus a small per-Page and per-start
charge on the free plan, as published by the Actor), so:

| Control | Setting |
|---|---|
| per-account interval (minimum 15 min) | `poll_interval_minutes` in the YAML |
| posts per run | `max_posts_per_run`, sent as `resultsLimit` and `maxItems`, enforced again locally |
| only new posts | `onlyPostsNewerThan` = time since last success + 6 h (48 h on the first poll); free filter |
| spend ceiling per run | `SOCIAL_MAX_CHARGE_USD_PER_RUN` (Apify stops the run) |
| run timeout | `SOCIAL_RUN_TIMEOUT_SECONDS` |
| runs per rolling day, all accounts | `SOCIAL_MAX_RUNS_PER_DAY` |
| master switch | `SOCIAL_INGESTION_ENABLED` (default **false**) |

A failed poll is retried after `SOCIAL_RETRY_AFTER_ERROR_MINUTES`; a refusal by the platform
(`blocked` status) waits the normal interval. A poll counts toward the daily budget as soon
as the Actor starts.

## Hand-off to the shared pipeline

Accepted posts become `pending` `source_items` (title = first line, excerpt = post text). The
pipeline screens them with the same Zimbabwe road keyword filter and redacts them, then:

* a plain post **skips article retrieval**: its redacted text becomes `article_text_redacted`
  and the item goes straight to `fetched`;
* a post whose `link` points outside Facebook is read **together with** that article (post
  first, then article); if the page is unreadable the post alone is used;
* OpenAI extraction, validation, deduplication, evidence linking and editorial review are
  unchanged. Incidents are only ever created as `candidate`.

Run status in `ingestion_runs`: `succeeded`; `partial` when something was rejected or
quarantined (see `error_message`); `failed` when the Actor failed or the platform refused the
account.

## Enabling X or TikTok

Nothing is enabled today, by design. To add a platform:

1. Choose an Actor that returns only the posts of a named account, read its published input
   and output schema, and confirm its terms permit your use. Do not guess an Actor id.
2. Write `app/ingestion/social/<platform>.py` implementing `PlatformAdapter` (`build_input`,
   `notice`, `judge`, `max_items`) with explicit origin checks like the Facebook adapter, and
   a test file modelled on `tests/test_social_adapter.py`.
3. Register it in `app/ingestion/social/registry.py`. Until then the YAML loader refuses
   `enabled: true` for that platform and the poller skips it even if the database says otherwise.

## Known limits

* The Actor's `note` row `reason` strings are not documented exhaustively; a status row counts as
  "account unreadable" only if its reason contains `not-found`, `blocked`, `refus`, `private`,
  `invalid`, `unsupported` or `login`. Check real notes after the first live runs.
* Facebook may show some Pages only to logged-in visitors; those return a free `not-found` row and
  the source is marked `blocked`. No login or access control is bypassed.
* Post text is redacted for phone numbers, e-mail addresses and similar patterns by the existing
  redaction step; names remain, as for RSS. Review the platform's terms and applicable privacy law
  before enabling an account.
* The web UI does not yet show social-specific fields (quarantine, platform); social sources
  appear in Data Sources as ordinary sources of kind `social`.
