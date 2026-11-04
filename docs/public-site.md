# SafeRouteZW public site

Login-free pages under `/public`: alerts, map, route planner, operator planner, SMS/WhatsApp alert subscriptions.

## Safety boundary
Public endpoints read only through `apps/api/app/repositories/public.py`: a `public_alerts` row with
`status = 'published'` (the database trigger requires a standing human approval of that exact bulletin
version) on an incident with `status = 'published'`. Approval never publishes: an editor must call
`POST /api/v1/incidents/{id}/publish` with the exact approved, latest `bulletin_version_id`.
`POST /api/v1/incidents/{id}/unpublish` withdraws it. Both are editor/admin only and audited.

## Run it
```
# API (apps/api)
alembic upgrade head                       # adds migration f6b8c4d0e2a3
python -m uvicorn app.main:app --port 8000
python scripts/run_notifications_once.py   # queue + (mock) deliver subscriber alerts
python scripts/demo_acceptance.py          # synthetic end-to-end walk-through (dev DB only)
python -m pytest                           # DB tests need POSTGRES_USER/PASSWORD in .env

# Web (apps/web)
python ../api/scripts/export_openapi.py && npm run api:types
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev    # open /public
```

## Configuration (root `.env`)
`GEOAPIFY_API_KEY` (place search + routing, required for `/public/routes`), `ROUTING_PROVIDER`
(`geoapify|mock|none`), `ROUTE_HAZARD_BUFFER_M`, `PUBLIC_CORS_ORIGINS`, `PUBLIC_RATE_LIMIT_PER_MINUTE`,
`PUBLIC_WRITE_RATE_LIMIT_PER_MINUTE`, `SUBSCRIBER_ENCRYPTION_KEY` (Fernet), `SUBSCRIBER_DIGEST_KEY`,
`NOTIFICATION_PROVIDER` (only `mock` exists), `MOCK_EXPOSE_CODES` (local demo only), `SUBSCRIPTION_CORRIDORS`,
`OTP_*`. Set both subscriber keys before real use.

## Limitations
No real SMS/WhatsApp provider yet (mock records messages in memory only). Road closures are not a data
type yet, so closures are always empty and nothing reroutes. No live traffic. The in-process rate limiter
is per API process. `notification_outbox` is unused; `subscriber_deliveries` is the per-recipient queue.
