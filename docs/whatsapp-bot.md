# WhatsApp bot

A menu-driven assistant on the official **Meta WhatsApp Business Cloud API**, with exactly three
functions. It is deterministic: no AI is used for menus or replies. OpenAI is used only by the
existing incident pipeline, after a report has been saved and redacted.

```
Welcome to SafeRouteZW 🇿🇼

1. Report a road incident
2. Road alerts
3. Check a route

Reply with 1, 2 or 3.
```

Buttons and list messages are used where WhatsApp supports them; typing `1`, `2`, `3` always works.
`MENU`, `BACK`, `CANCEL`, `HELP` navigate; `STOP` (or `UNSUBSCRIBE`) ends alert subscriptions from anywhere.

## What it does

| Function | Behaviour |
| --- | --- |
| **Report a road incident** | where (text or location pin) → what → when → summary → confirm. Saved as a `source_items` row of the `WhatsApp public reports` source (`kind=whatsapp`, `unverified`). The sender gets a reference (`WA-XXXXXXXX`) and "Your report has been received for review." It then follows the normal pipeline (redaction → OpenAI → **candidate** incident) and **an editor must approve it** before anything is public. Location and time are stored as the sender's claims; a pin is stored with `origin: whatsapp_location_pin`. Photos are **not accepted** (no media pipeline exists); the user is told a written report is enough. |
| **Road alerts** | Subscribe / Manage / Unsubscribe on the existing subscriber domain: areas (All Zimbabwe, provinces, configured corridors) → explicit consent text → one-time code sent over WhatsApp → `active`. Nothing is active before both consent and the code. Messaging the bot or sending a report never subscribes anyone. |
| **Check a route** | origin → destination (ambiguous places show a list of up to 5 to choose from) → `plan_route` (the public routing service) → short reply with the real distance, duration estimate, count and top 3 published alerts near the route, a link to the public results, and the standard disclaimer. If geocoding or routing is down it says route checking is temporarily unavailable; it never estimates. |

## Architecture

```
Meta ──POST──▶ /api/v1/webhooks/whatsapp ──▶ whatsapp_inbound (unique wamid)   ◀── fast, no logic
                  verify X-Hub-Signature-256            │
                                                         ▼
                      worker (scheduler job `whatsapp_dispatch`, SKIP LOCKED claims)
                         conversation engine ─▶ incident_intake / subscriptions / route_check
                                │                         │              │
                                │                  source_items   services.subscriptions   route_planning
                                ▼                   (→ pipeline)        + alert outbox       + PostGIS
                         whatsapp_outbound (idempotent replies) ──▶ MetaCloudClient (or the mock)
Delivery receipts ──▶ webhook ──▶ whatsapp_outbound / subscriber_deliveries
```

* **Webhook** (`app/api/v1/webhooks.py`): GET handshake; POST verifies the HMAC of the *raw body*, stores
  messages, applies delivery statuses, returns 200. Invalid signature → 401, nothing stored.
  Duplicate deliveries are harmless (unique message id). Senders over `WHATSAPP_USER_MSGS_PER_MINUTE` are dropped.
* **Worker** (`app/jobs/whatsapp_dispatch.py`): claims pending messages (oldest *send time* first),
  runs the conversation, retries up to `WHATSAPP_MAX_ATTEMPTS`, then marks the message failed and sends one apology.
  It also delivers WhatsApp alert deliveries and purges old data. Run by `python -m app.jobs.scheduler`
  when `WHATSAPP_ENABLED=true`, or once with `python scripts/run_whatsapp_once.py`.
* **State** lives in PostgreSQL (`whatsapp_conversations`: flow, step, draft, expiry). An idle session
  (`WHATSAPP_SESSION_TTL_MINUTES`, default 30) is reset to the menu and its draft erased.
* **Privacy**: senders are stored as a keyed digest plus Fernet ciphertext (needed to reply). Message
  text is removed from `whatsapp_inbound` as soon as it is handled. Reports are redacted before they are
  stored and carry only a sender digest, never the phone number. Finished rows are purged after
  `WHATSAPP_RETENTION_DAYS`. Logs contain no tokens, numbers or message text.

## Alert delivery

Published, human-approved alerts reach verified, consenting WhatsApp subscribers through the existing
`subscriber_deliveries` outbox (`alert_notifications`): published-only, consent re-checked at send time,
one delivery per alert/subscriber (unique key), retries with backoff, `unknown` outcomes not re-sent.
`WhatsAppMetaProvider` sends codes and confirmations as session text and alerts as your **approved
template** (`WHATSAPP_ALERT_TEMPLATE_NAME`). Without a template an alert is sent as session text, which
Meta rejects outside the 24-hour window (error 131047); that delivery is then recorded as failed.
Set `NOTIFICATION_PROVIDER=whatsapp_meta` for real alert delivery.

### Template to register (WhatsApp Manager → Message templates)

Body, one variable:  `{{1}}`  — the alert text already ends with "Reply STOP to unsubscribe." and a link.
Which category Meta assigns to a road-safety alert (utility vs marketing) is Meta's decision, as are
the price and approval; do not assume it. Test sends need a template in `APPROVED` state.

## Try it without WhatsApp or charges

```powershell
cd apps/api
python scripts/simulate_whatsapp.py                    # all three functions, scripted
python scripts/simulate_whatsapp.py --scenario report
python scripts/simulate_whatsapp.py --interactive      # type as the user: text, tap:2, pin:-17.8,31.0, photo
python scripts/simulate_whatsapp.py --keep             # keep the rows (default: rolled back)
```

It uses your database (inside a transaction that is rolled back), a mock messenger, a handful of
built-in towns and straight-line routes. It refuses to run unless `NOTIFICATION_PROVIDER=mock`.
Webhook fixtures for manual `curl` tests are in `apps/api/tests/test_whatsapp_webhook.py`.

## Connect real WhatsApp (when you are ready)

1. **Meta developer app**: developers.facebook.com → create an app of type *Business* → add the *WhatsApp* product.
2. **Test number**: WhatsApp → API Setup gives a free test number and a temporary token. Add your own phone as a
   recipient (only listed recipients can be messaged with the test number). Copy the *Phone number ID* and *Business account ID*.
3. **Permanent token**: Business settings → System users → create one, assign the WhatsApp account, generate a
   token with `whatsapp_business_messaging` (and `whatsapp_business_management`). Keep it server-side only.
4. **App secret**: App settings → Basic → *App secret*.
5. **`.env`** (never commit):
   ```
   WHATSAPP_ENABLED=true
   WHATSAPP_VERIFY_TOKEN=<random string you invent>
   WHATSAPP_APP_SECRET=<app secret>
   WHATSAPP_ACCESS_TOKEN=<token>
   WHATSAPP_PHONE_NUMBER_ID=<id>
   WHATSAPP_BUSINESS_ACCOUNT_ID=<id>
   WHATSAPP_GRAPH_API_VERSION=v23.0   # confirm the current version in Meta's changelog
   WHATSAPP_SEND_MODE=mock            # change to live only after the webhook test below
   SUBSCRIBER_ENCRYPTION_KEY=...      # required once NOTIFICATION_PROVIDER is not mock
   SUBSCRIBER_DIGEST_KEY=...
   ```
6. **Local HTTPS tunnel** for the webhook (Meta requires HTTPS), e.g. `cloudflared tunnel --url http://localhost:8000`
   or `ngrok http 8000`. Use a tunnel you control and stop it when finished; the URL is public.
7. **Webhook**: WhatsApp → Configuration → Callback URL `https://<tunnel>/api/v1/webhooks/whatsapp`, Verify token = your
   `WHATSAPP_VERIFY_TOKEN` → *Verify and save*, then subscribe to the **messages** field.
8. Start the API (`uvicorn app.main:app`) and the scheduler (`python -m app.jobs.scheduler`). Message the test number
   from your phone: with `WHATSAPP_SEND_MODE=mock` the bot processes but does not reply (check the logs);
   set `live` to reply for real.
9. Production: a registered business phone number, a verified business, an approved alert template, and
   `COOKIE_SECURE`/HTTPS on the API host.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `WHATSAPP_ENABLED` | false | Webhook returns 404 and the job idles while false. |
| `WHATSAPP_SEND_MODE` | mock | `live` is the only mode that contacts Meta. Needs token + phone number id. |
| `WHATSAPP_APP_SECRET` / `WHATSAPP_VERIFY_TOKEN` | – | Webhook authenticity and handshake. Without the app secret every POST is refused. |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID` | – | Cloud API credentials. |
| `WHATSAPP_GRAPH_API_VERSION` | v23.0 | Not verified against Meta's current changelog when written. |
| `WHATSAPP_API_TIMEOUT_SECONDS` / `WHATSAPP_API_MAX_RETRIES` | 10 / 2 | Retries only 429/5xx and connection failures; a read timeout is reported `unknown`, not retried. |
| `WHATSAPP_ALERT_TEMPLATE_NAME` / `_LANGUAGE` | – / en | Approved template for alerts. |
| `WHATSAPP_SESSION_TTL_MINUTES` | 30 | Idle conversation reset. |
| `WHATSAPP_USER_MSGS_PER_MINUTE` | 20 | Per-sender flood limit. |
| `WHATSAPP_DISPATCH_INTERVAL_SECONDS` / `_BATCH_SIZE` | 15 / 50 | Worker cadence and bound. |
| `WHATSAPP_MAX_ATTEMPTS` | 3 | Processing attempts per message. |
| `WHATSAPP_RETENTION_DAYS` | 30 | Purge of finished messages, idle sessions, send log. |
| `PUBLIC_WEB_BASE_URL` | http://localhost:3000 | Base for links in replies and alerts. |

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Webhook verification fails in Meta | `WHATSAPP_ENABLED=true`, token matches exactly, tunnel URL ends in `/api/v1/webhooks/whatsapp`. API log shows no request → tunnel/URL issue. |
| Messages arrive (401 in log: "bad or missing signature") | `WHATSAPP_APP_SECRET` is wrong or missing. |
| Messages stored but no reply | Scheduler not running, or `WHATSAPP_SEND_MODE=mock`. `select status, count(*) from whatsapp_inbound group by 1`. |
| `failed` inbound rows | `last_error` holds the exception class only. See the worker log for the traceback. |
| Reply sent but not delivered, `131047` | The 24-hour window closed: send a template. |
| No alerts to a subscriber | Subscriber must be `active` with consent; alert must be `published` within 48 h and after the subscriber's verification; `NOTIFICATION_PROVIDER=whatsapp_meta`; template approved. |
| "Route checking is temporarily unavailable" | `GEOAPIFY_API_KEY`, `GEOCODER`, `ROUTING_PROVIDER` (not `none`). |

Useful queries: `whatsapp_inbound` (queue), `whatsapp_outbound` (send log with delivery status),
`whatsapp_conversations` (sessions), `subscriber_deliveries` (alert outbox).

## Known limits

* Photos are not accepted. Adding them needs a media download, malware/EXIF handling and storage design first.
* Delivery-status callbacks for a reply can arrive before its message id is saved; that status is skipped.
* The per-sender rate limit is in process memory (like the public API's); run one API worker or move it to the database.
* Language is English only.
