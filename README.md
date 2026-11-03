# SafeRouteZW

SafeRouteZW is an AI-assisted road safety intelligence and newsroom co-pilot for
Zimbabwe. The planned platform will turn unstructured traffic reports from
WhatsApp, social media, RSS feeds, and webhooks into information for editorial
review. **Every incident alert must receive human editorial approval before
publication.** Approval and publishing are future work; no alert publishing
exists in this foundation.

This repository currently provides a working FastAPI health endpoint,
configuration, and the **database layer**: 16 SQLAlchemy models on PostgreSQL +
PostGIS, managed entirely by Alembic migrations. Ingestion, extraction,
geospatial scoring, authentication, and editorial workflow logic are not
implemented. Other reserved Python modules contain documentation only.

## Technology stack

- Python 3.11+ and FastAPI, served by Uvicorn.
- SQLAlchemy 2.x, psycopg 3, GeoAlchemy2, and Alembic for the database layer.
- A locally installed PostgreSQL (developed against 18) with the PostGIS
  extension. No Docker is used.
- Local Ollama with `qwen2.5:7b` for future extraction.
- Next.js is planned for the editorial dashboard; no frontend is initialized.
- pytest and HTTPX for backend checks.

## Repository structure

```text
apps/
  api/
    app/
      main.py           # GET /health
      api/v1/           # Reserved incident, review, blackspot, public routes
      core/             # Settings, lazy engine/session, geo helpers, db_check
      models/           # The 16 ORM models (see Database below)
      schemas/          # Reserved
      services/         # Reserved; no business logic
      repositories/     # Reserved
    alembic.ini         # No credentials; the URL comes from app settings
    alembic/            # env.py, script.py.mako, versions/ (the only schema mechanism)
    tests/              # Unit tests + database integration tests
    pyproject.toml      # Dependency source of truth
    requirements.txt    # Installs the project and development dependencies
  web/                  # Intentionally completely empty
infra/
  docker/               # Reserved
  sql/                  # PostGIS initialization only (legacy; Alembic now enables PostGIS)
data/
  blackspots/           # Private local datasets; ignored by Git
  samples/              # No invented reports or sample accident records
docs/
scripts/
.github/workflows/      # Reserved
docker-compose.yml      # Legacy and unused: the project uses a local PostgreSQL
.env.example
.gitignore
```

`apps/web/` must remain empty: no `package.json`, Next.js files, dependencies, or
`.gitkeep`. Git cannot store empty directories, so recreate it after cloning:
`New-Item -ItemType Directory -Force apps/web` (PowerShell), or
`mkdir -p apps/web` (bash). Other reserved directories use `.gitkeep` where needed.

## Prerequisites

Install Python 3.11+ with pip, Git, and PostgreSQL 13 or newer (13+ provides the
built-in `gen_random_uuid()`), with the **PostGIS** extension installed for your
PostgreSQL version. On Windows, install PostGIS from Stack Builder (Spatial
Extensions) or the PostGIS Windows bundle matching your PostgreSQL version, then
restart the PostgreSQL service if the installer asks. The database user needs
`CREATEDB` (or create the `saferoutezw` and `saferoutezw_test` databases yourself).

Ollama is optional for this phase. No startup command or dependency installation
downloads the model or contacts Ollama. When extraction development begins, a
local Ollama server and a separately provisioned model will be needed.

## Local development

Run the following from the repository root. The folder name may be `saferoutezw`;
no additional nested project folder is required.

### PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

### bash / macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Edit `.env` and set `POSTGRES_USER` and `POSTGRES_PASSWORD` for your local
PostgreSQL server (host, port, and database names have defaults). Do not URL-encode
the password: the connection URL is built in code with `URL.create()`, which
escapes special characters. Keep credentials local: `.env` and other local
environment files are ignored by Git. `.env.example` contains placeholders only,
and passwords are never printed or written to `alembic.ini`.

The API reads the root `.env` regardless of the current working directory.
Operating-system environment variables override values from the file.

Install the backend from the activated virtual environment:

```bash
cd apps/api
python -m pip install -r requirements.txt
```

### Database

Run these from `apps/api`. Alembic is the only way schema is created or changed;
`Base.metadata.create_all()` is never used.

```bash
python -m app.core.db_check          # connectivity, server version, PostGIS, migration state
alembic upgrade head                 # create the schema (enables PostGIS, 16 tables, triggers)
alembic current                      # revision the database is at
alembic heads                        # latest revision in the code (they should match)
alembic downgrade base               # remove application objects; PostGIS is left installed
alembic revision --autogenerate -m "describe change"   # then review the file by hand
```

The first time, create the empty database if it does not exist yet (the database
named by `POSTGRES_DB`, default `saferoutezw`). `alembic upgrade head` fails with
a clear error if PostGIS is not installed on the server.

The 16 tables, by area: **ingestion** `sources`, `ingestion_runs`, `source_items`;
**incidents** `incidents`, `incident_evidence`, `extraction_runs`; **geospatial**
`blackspots`, `incident_blackspot_matches`; **editorial** `users`,
`bulletin_versions`, `editorial_reviews`; **alerts** `public_alerts`,
`delivery_channels`, `notification_outbox`, `delivery_attempts`; **audit**
`audit_events`.

Safeguards enforced by the database itself (see the initial migration):

- Only an **active human editor** (`admin`/`editor`) can record an editorial
  decision. `service` accounts, such as an AI pipeline, can draft but never review.
- An incident cannot become `approved`/`published` without an approving review.
- A `public_alerts` row cannot be inserted or published unless its approving
  review exists, is `approved`, covers the same incident and bulletin version, was
  made by an active human editor, and was not superseded by a later decision.
- `bulletin_versions`, `editorial_reviews` and `audit_events` are append-only, so
  an approval always refers to the exact text that was reviewed.
- Foreign keys on editorial and evidence history use `ON DELETE RESTRICT`.
- Points are `Geography(POINT, 4326)`; WKT order is `POINT(longitude latitude)`.
  Build them with `app.core.geo.point_from_lat_lon(latitude, longitude)`.

For production, run the API as a dedicated role that owns no schema and is
granted only `SELECT`/`INSERT` on `audit_events`, rather than as `postgres`.

Start the API:

```bash
uvicorn app.main:app --reload
```

The default address is `http://127.0.0.1:8000`. `API_HOST` and `API_PORT` are
available in application settings; the Uvicorn CLI uses its own flags. If you
change those values, pass the matching `--host` and `--port` flags when launching
Uvicorn. API docs are available at `http://127.0.0.1:8000/docs`.

### Verify the API

Open `http://127.0.0.1:8000/health`, or use:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

```bash
curl http://127.0.0.1:8000/health
```

Expected JSON:

```json
{"status":"ok","service":"saferoutezw-api","version":"0.1.0"}
```

This endpoint reports process health; it does not check database or Ollama
readiness and can run without either service or a `.env` file.

Run backend checks from `apps/api`:

```bash
python -c "from app.main import app; print(app.title)"
python -m pytest
python -m pip check
```

Database integration tests run against a **separate** database,
`POSTGRES_TEST_DB` (default `saferoutezw_test`). It is created on demand, migrated
with Alembic, and truncated between tests. The tests refuse to run unless its name
ends in `_test` and differs from `POSTGRES_DB`, so the development database is
never touched. They are skipped if PostgreSQL is unreachable and fail with a clear
message if PostGIS is missing.

## Configuration

| Variable | Purpose |
| --- | --- |
| `POSTGRES_HOST` / `POSTGRES_PORT` | Local PostgreSQL server, default `localhost:5432` |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | Credentials (required to use the database) |
| `POSTGRES_DB` | Application database, default `saferoutezw` |
| `POSTGRES_TEST_DB` | Disposable test database, default `saferoutezw_test` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint, `http://localhost:11434` |
| `OLLAMA_MODEL` | Future extraction model, `qwen2.5:7b` |
| `API_HOST` | Application host setting, defaults to `127.0.0.1` |
| `API_PORT` | Application port setting, defaults to `8000` |

Dependencies are declared in `apps/api/pyproject.toml`; `requirements.txt` installs
that project with the `dev` extra. Version ranges are bounded but not locked.
Dataset contents under `data/` are ignored by default; review provenance and
privacy before deliberately versioning any future dataset.

Health testing follows the
[FastAPI testing documentation](https://fastapi.tiangolo.com/tutorial/testing/).
