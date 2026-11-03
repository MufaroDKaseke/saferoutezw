# SafeRouteZW

SafeRouteZW is an AI-assisted road safety intelligence and newsroom co-pilot for
Zimbabwe. The planned platform will turn unstructured traffic reports from
WhatsApp, social media, RSS feeds, and webhooks into information for editorial
review. **Every incident alert must receive human editorial approval before
publication.** Approval and publishing are future work; no alert publishing
exists in this foundation.

This repository currently provides a working FastAPI health endpoint, local
database infrastructure, and configuration. Ingestion, extraction, geospatial
scoring, authentication, editorial workflows, application tables, and migrations
are not implemented. Reserved Python modules contain documentation only.

## Technology stack

- Python 3.11+ and FastAPI, served by Uvicorn.
- SQLAlchemy, psycopg, GeoAlchemy2, and Alembic for future database work.
- PostgreSQL 17 and PostGIS 3.5, managed locally with Docker Compose.
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
      core/             # Configuration, lazy database engine, security boundary
      models/           # Reserved; no application tables
      schemas/          # Reserved
      services/         # Reserved; no business logic
      repositories/     # Reserved
    alembic/            # Reserved; no migrations yet
    tests/
    pyproject.toml      # Dependency source of truth
    requirements.txt    # Installs the project and development dependencies
  web/                  # Intentionally completely empty
infra/
  docker/               # Reserved
  sql/                  # PostGIS initialization only
data/
  blackspots/           # Private local datasets; ignored by Git
  samples/              # No invented reports or sample accident records
docs/
scripts/
.github/workflows/      # Reserved
docker-compose.yml
.env.example
.gitignore
```

`apps/web/` must remain empty: no `package.json`, Next.js files, dependencies, or
`.gitkeep`. Git cannot store empty directories, so recreate it after cloning:
`New-Item -ItemType Directory -Force apps/web` (PowerShell), or
`mkdir -p apps/web` (bash). Other reserved directories use `.gitkeep` where needed.

## Prerequisites

Install Python 3.11+ with pip, Git, and Docker with the Compose v2 plugin. Start
Docker Desktop (using Linux containers on Windows) or the Docker engine before
starting the database. Port 5432 must be available locally.

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

Edit `.env` and replace the example password in both `POSTGRES_PASSWORD` and
`DATABASE_URL`. URL-encode reserved characters in the URL password. The database
and database user are both `saferoutezw`. Keep credentials local: `.env` and other
local environment files are ignored by Git. `.env.example` contains development
placeholders only.

The API reads the root `.env` regardless of the current working directory.
Operating-system environment variables override values from the file.

Start the database from the repository root:

```bash
docker compose up -d db
docker compose ps
docker compose exec db psql -U saferoutezw -d saferoutezw -c "SELECT PostGIS_Version();"
```

PostgreSQL is exposed only on `127.0.0.1:5432`. A named volume persists its data.
The initialization SQL enables PostGIS and creates no application tables.
Initialization scripts and the initial password apply on the first startup of an
empty volume; editing `.env` does not change an existing database password.

Install the backend and start it from the activated virtual environment:

```bash
cd apps/api
python -m pip install -r requirements.txt
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

From the repository root, validate Compose without printing credentials:

```bash
docker compose config --quiet
```

To stop the database while retaining its data, run `docker compose stop db`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `POSTGRES_PASSWORD` | Required by Compose for the local database |
| `DATABASE_URL` | SQLAlchemy URL using the `postgresql+psycopg` driver |
| `OLLAMA_BASE_URL` | Local Ollama endpoint, `http://localhost:11434` |
| `OLLAMA_MODEL` | Future extraction model, `qwen2.5:7b` |
| `API_HOST` | Application host setting, defaults to `127.0.0.1` |
| `API_PORT` | Application port setting, defaults to `8000` |

Dependencies are declared in `apps/api/pyproject.toml`; `requirements.txt` installs
that project with the `dev` extra. Version ranges are bounded but not locked.
Dataset contents under `data/` are ignored by default; review provenance and
privacy before deliberately versioning any future dataset.

The infrastructure and health testing follow the upstream
[PostGIS Docker image documentation](https://github.com/postgis/docker-postgis)
and [FastAPI testing documentation](https://fastapi.tiangolo.com/tutorial/testing/).
