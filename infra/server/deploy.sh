#!/usr/bin/env bash
# Runs on the server, as the app user, after CI has synced the code into /opt/saferoutezw/app.
# (CI builds the web app, so apps/web/.next arrives prebuilt.) Idempotent; also usable by hand:
#
#   ssh saferoute@<server> 'bash /opt/saferoutezw/app/infra/server/deploy.sh'
#
# Steps: Python deps -> web deps -> (fallback build) -> DB backup + migrations -> pm2 reload -> health checks.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/saferoutezw}"
APP_DIR="$APP_ROOT/app"
VENV="$APP_ROOT/venv"
STATE="$APP_ROOT/.deploy-state"   # hashes of the dependency files last installed
BACKUPS="$APP_ROOT/backups"       # pre-migration dumps (the nightly ones live in /var/backups)

log() { printf '\n==> %s\n' "$*"; }
on_error() { echo; echo "Deploy failed. Recent process logs:"; pm2 logs --nostream --lines 30 2>/dev/null || true; }
die() { echo "ERROR: $*" >&2; on_error; exit 1; }
trap on_error ERR

cd "$APP_DIR"
[ -f .env ] || die "$APP_DIR/.env is missing; run infra/server/bootstrap.sh first"
mkdir -p "$STATE" "$BACKUPS"

env_value() { grep -E "^$1=" "$APP_DIR/.env" | head -1 | cut -d= -f2-; }

# ---------------------------------------------------------------------------------------------
log "Python dependencies"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
want="$(sha256sum apps/api/pyproject.toml | cut -d' ' -f1)"
if [ "$(cat "$STATE/python" 2>/dev/null || true)" != "$want" ]; then
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -e apps/api
  echo "$want" > "$STATE/python"
else
  echo "pyproject.toml unchanged; skipping install"
fi

# ---------------------------------------------------------------------------------------------
log "Web dependencies"
cd apps/web
want="$(sha256sum package-lock.json | cut -d' ' -f1)"
if [ ! -d node_modules ] || [ "$(cat "$STATE/node" 2>/dev/null || true)" != "$want" ]; then
  pm2 stop saferoute-web >/dev/null 2>&1 || true   # npm ci replaces node_modules under a running server
  npm ci --no-audit --no-fund
  echo "$want" > "$STATE/node"
else
  echo "package-lock.json unchanged; skipping install"
fi

if [ ! -f .next/BUILD_ID ]; then
  log "No prebuilt .next from CI; building here (slow; relies on the swap file)"
  set -a; . "$APP_DIR/infra/server/web.env"; set +a
  NODE_OPTIONS=--max-old-space-size=1536 npm run build
fi
cd "$APP_DIR"

# ---------------------------------------------------------------------------------------------
log "Database migrations"
cd apps/api
current="$("$VENV/bin/alembic" current 2>/dev/null || true)"   # captured first: grep -q in a pipe can SIGPIPE it
if ! grep -q '(head)' <<<"$current"; then
  backup="$BACKUPS/pre-migration-$(date -u +%Y%m%dT%H%M%SZ).dump"
  echo "Schema is not at head; saving $backup first"
  PGPASSWORD="$(env_value POSTGRES_PASSWORD)" pg_dump -h "$(env_value POSTGRES_HOST)" \
    -U "$(env_value POSTGRES_USER)" --format=custom --file="$backup" "$(env_value POSTGRES_DB)"
  ls -1t "$BACKUPS"/pre-migration-*.dump | tail -n +6 | xargs -r rm -f   # keep the newest 5
  "$VENV/bin/alembic" upgrade head
else
  echo "Already at head"
fi
# Registers any feeds added to the code; existing sources are left exactly as they are.
"$VENV/bin/python" scripts/seed_rss_sources.py
cd "$APP_DIR"

# ---------------------------------------------------------------------------------------------
log "Restarting processes (pm2)"
pm2 startOrReload infra/server/ecosystem.config.cjs --update-env
pm2 save --force >/dev/null

# ---------------------------------------------------------------------------------------------
log "Health checks"
wait_for() {
  local name="$1" url="$2" code="000"
  for _ in $(seq 1 45); do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" || true)"
    case "$code" in 2* | 3*) echo "$name is up (HTTP $code)"; return 0 ;; esac
    sleep 2
  done
  die "$name did not come up at $url (last status $code)"
}
wait_for "API          " http://127.0.0.1:8000/health
wait_for "Web          " http://127.0.0.1:3000/
wait_for "Web -> API   " http://127.0.0.1:3000/backend/health

echo
pm2 status
log "Deploy complete"
