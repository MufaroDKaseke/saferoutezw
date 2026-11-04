# SafeRouteZW web

The editorial dashboard for SafeRouteZW: news monitoring, AI-assisted incident
intelligence, a safety map, and human editorial review. **The AI suggests. A
named editor decides what, if anything, becomes public.**

Next.js 16 (App Router, Cache Components) · TypeScript · Tailwind CSS v4 ·
shadcn/ui (Radix, Nova preset) · Lucide · React Leaflet · Recharts · TanStack
Table v9 · Vitest + Testing Library.

## Run it

```bash
cd apps/web
npm install
cp .env.example .env.local      # optional; the defaults give the demo
npm run dev                     # http://localhost:3000
```

| Command | What it does |
| --- | --- |
| `npm run dev` | Development server (Turbopack). |
| `npm run build` | Production build. Typechecks and prerenders every route. |
| `npm run start` | Serve the production build. |
| `npm run lint` | ESLint. |
| `npm run typecheck` | `tsc --noEmit`. |
| `npm test` | Vitest, once. On a small machine use `npx vitest run --maxWorkers=1 --no-file-parallelism`. |

## Data modes

One setting controls the whole app: `NEXT_PUBLIC_DATA_MODE`.

- **`mock`** (default). Every page runs on the synthetic dataset in
  `src/lib/mock`. A permanent "Demo data" label shows in the header and sidebar.
  Actions (approve, reject, retry, add a source) change an in-memory copy, are
  flagged `simulated`, and reset on a full page reload or from Settings. Nothing
  reaches PostgreSQL, WhatsApp, SMS or any API.
- **`api`**. Pages call the FastAPI backend through the same-origin `/backend/*`
  proxy (the backend has no CORS). The backend only serves `GET /health`, so any
  other page shows **"Not available yet"** with the missing endpoint named. No
  data is invented.

The list of real endpoints lives in one place, `IMPLEMENTED_ENDPOINTS` in
[`src/lib/api/client.ts`](src/lib/api/client.ts). A call to anything not listed
throws before a request is sent. When the backend ships an endpoint, add it
there and fill in the response type.

## Environment

See [`.env.example`](.env.example): `NEXT_PUBLIC_DATA_MODE`,
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_MOCK_LATENCY_MS`, and the map tile URL and
attribution. Never put a secret in a `NEXT_PUBLIC_*` variable.

## Pages

`/dashboard` · `/news`, `/news/[id]` · `/incidents`, `/incidents/[id]` ·
`/reviews`, `/reviews/[id]` · `/map` · `/blackspots` · `/alerts`, `/alerts/[id]`
· `/sources` · `/processing` · `/settings` · `/login`

## Product safeguards the UI enforces

- **Article ≠ incident.** One article can feed several incidents, and several
  articles can support one.
- **Relevance ≠ verification.** A keyword match only means "read further".
- **AI extraction ≠ approval.** Everything the AI produced is marked indigo and
  labelled a suggestion.
- **Approval ≠ distribution.** An approved bulletin shows "Approved, not yet
  sent" until a channel confirms delivery, and each channel records its own
  attempts.
- **Blackspot proximity ≠ confirmation.** Credibility and geographic risk are
  separate assessments.
- Rejecting needs a reason. Approving needs an explicit confirmation of the exact
  bulletin text, and approval is blocked while the text contains sender details.

## Layout

```text
src/
  app/(dashboard)/…   routes (thin; they render the views below)
  app/(auth)/login
  components/         layout, shared, dashboard, news, incidents, editorial,
                      maps, alerts, sources, processing, settings, auth, ui
  hooks/              use-resource, use-list-state, use-demo-session, …
  lib/api/            the only place the app talks to the backend
  lib/mock/           synthetic dataset, in-memory store, simulated actions
  lib/domain/         pure rules (review state, alert state, bulletin checks)
  lib/formatters/     dates (Central Africa Time) and plain-language labels
  types/              domain types aligned with apps/api/app/models/enums.py
```

The visual reference is in [`docs/design/concept`](../../docs/design/concept).

## Notes for working on it

- This is Next 16 with **Cache Components**. Reading `params` or `usePathname()`
  is request-time data and must sit inside `<Suspense>`; see
  `components/shared/id-route.tsx` and `app/(dashboard)/layout.tsx`.
- Leaflet only runs in the browser (`maps/safety-map-loader.tsx`).
- The default map tiles are OpenStreetMap's. Read their tile usage policy before
  production use, or point `NEXT_PUBLIC_MAP_TILE_URL` at a provider you have
  rights to.
- There is no authentication backend. `/login` opens a labelled demo session in
  mock mode, and role checks in the browser are a convenience, never security.
