#!/usr/bin/env bash
# Provision a fresh Ubuntu 24.04 server for SafeRouteZW: nginx + TLS, Node + pm2, Python,
# and a local PostgreSQL/PostGIS database. Run as root. Safe to re-run: every step checks
# the current state first, and existing secrets are never regenerated.
#
#   DOMAIN=saferoute.momo.co.zw ./bootstrap.sh
#
# Optional environment:
#   DEPLOY_PUBLIC_KEY   an SSH public key (one line) allowed to log in as the app user, for CI deploys
#   SKIP_TLS=1          skip the Let's Encrypt step (e.g. DNS not pointed yet)
set -euo pipefail

DOMAIN="${DOMAIN:-saferoute.momo.co.zw}"
APP_USER="${APP_USER:-saferoute}"
APP_ROOT="${APP_ROOT:-/opt/saferoutezw}"
APP_DIR="$APP_ROOT/app"
DB_NAME="${DB_NAME:-saferoutezw}"
DB_USER="${DB_USER:-saferoute}"
NODE_MAJOR="${NODE_MAJOR:-24}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
PUBLIC_URL="https://$DOMAIN"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a

log() { printf '\n==> %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
[ "$(id -u)" -eq 0 ] || { echo "Run as root." >&2; exit 1; }

as_postgres() { runuser -u postgres -- "$@"; }

# ---------------------------------------------------------------------------------------------
log "Swap (the build and npm install peak above the 2 GB of RAM)"
if ! swapon --show --noheadings | grep -q .; then
  fallocate -l "$SWAP_SIZE" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/99-saferoute.conf
sysctl -q -p /etc/sysctl.d/99-saferoute.conf

# ---------------------------------------------------------------------------------------------
log "System packages"
apt-get update -qq
apt-get install -y -qq \
  ca-certificates curl gnupg rsync ufw fail2ban logrotate \
  nginx certbot \
  postgresql postgresql-contrib postgresql-16-postgis-3 \
  python3 python3-venv python3-pip python3-dev build-essential

log "Node.js $NODE_MAJOR (NodeSource) and pm2"
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" != "$NODE_MAJOR" ]; then
  install -d -m 755 /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
    > /etc/apt/sources.list.d/nodesource.list
  apt-get update -qq
  apt-get install -y -qq nodejs
fi
command -v pm2 >/dev/null || npm install -g pm2 --silent --no-fund --no-audit

# ---------------------------------------------------------------------------------------------
log "App user and directories"
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "$APP_USER"
  passwd -l "$APP_USER" >/dev/null   # key-only: no password login
fi
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$APP_ROOT" "$APP_DIR"

if [ -n "${DEPLOY_PUBLIC_KEY:-}" ]; then
  install -d -m 700 -o "$APP_USER" -g "$APP_USER" "/home/$APP_USER/.ssh"
  AUTH="/home/$APP_USER/.ssh/authorized_keys"
  touch "$AUTH"; chmod 600 "$AUTH"; chown "$APP_USER:$APP_USER" "$AUTH"
  # `restrict` disables port/agent/X11 forwarding and ptys; deploys only need rsync and a shell command.
  grep -qF "$DEPLOY_PUBLIC_KEY" "$AUTH" || echo "restrict $DEPLOY_PUBLIC_KEY" >> "$AUTH"
fi

# ---------------------------------------------------------------------------------------------
log "PostgreSQL + PostGIS"
PG_CONF_DIR="$(ls -d /etc/postgresql/*/main | sort -V | tail -1)"
PG_TUNING="$PG_CONF_DIR/conf.d/99-saferoute.conf"
cat > "$PG_TUNING.new" <<'EOF'
# Managed by infra/server/bootstrap.sh. Sized for a 2 GB host shared with Node and Python.
listen_addresses = 'localhost'
max_connections = 50
shared_buffers = 256MB
effective_cache_size = 768MB
work_mem = 8MB
maintenance_work_mem = 64MB
EOF
systemctl enable --now postgresql >/dev/null
if cmp -s "$PG_TUNING.new" "$PG_TUNING"; then
  rm -f "$PG_TUNING.new"          # unchanged: leave a running database alone
else
  mv "$PG_TUNING.new" "$PG_TUNING"
  systemctl restart postgresql    # shared_buffers / max_connections only apply after a restart
fi

ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  DB_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
else
  DB_PASSWORD="$(openssl rand -hex 24)"
fi

# Passwords go through stdin so they never appear in a process list.
if as_postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  echo "ALTER ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD';" | as_postgres psql -v ON_ERROR_STOP=1 -q
else
  echo "CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD';" | as_postgres psql -v ON_ERROR_STOP=1 -q
fi
as_postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 \
  || as_postgres createdb --owner="$DB_USER" "$DB_NAME"
# CREATE EXTENSION needs a superuser; the Alembic migration then finds PostGIS already enabled.
as_postgres psql -v ON_ERROR_STOP=1 -q -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis;"

if [ ! -f "$ENV_FILE" ]; then
  log "Writing $ENV_FILE (new secrets generated; fill in the third-party keys by hand)"
  umask 077
  cat > "$ENV_FILE" <<EOF
# Production settings for SafeRouteZW. Generated by infra/server/bootstrap.sh; never committed.
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASSWORD
POSTGRES_DB=$DB_NAME

API_HOST=127.0.0.1
API_PORT=8000

# HTTPS-only cookies, and the origin the browser sends state-changing requests from.
COOKIE_SECURE=true
TRUSTED_ORIGINS=$PUBLIC_URL
PUBLIC_WEB_BASE_URL=$PUBLIC_URL
# nginx overwrites X-Forwarded-For with the real client address, so it is safe to trust here.
TRUST_FORWARDED_FOR=true

# Subscriber data protection (generated once; losing these makes stored phone numbers unreadable).
SUBSCRIBER_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
SUBSCRIBER_DIGEST_KEY=$(openssl rand -hex 32)
NOTIFICATION_PROVIDER=mock
MOCK_EXPOSE_CODES=false

# --- Third-party keys: fill in as features are switched on ---------------------------------
OPENAI_API_KEY=
GEOAPIFY_API_KEY=
GOOGLE_MAPS_API_KEY=
APIFY_API_TOKEN=
SOCIAL_INGESTION_ENABLED=false
WHATSAPP_ENABLED=false
WHATSAPP_SEND_MODE=mock
EOF
  chown "$APP_USER:$APP_USER" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

# ---------------------------------------------------------------------------------------------
log "Nightly database backup"
install -m 755 "$SRC_DIR/backup-db.sh" /usr/local/sbin/saferoute-backup-db
cat > /etc/cron.d/saferoute-backup <<EOF
# Managed by infra/server/bootstrap.sh
30 2 * * * root DB_NAME=$DB_NAME /usr/local/sbin/saferoute-backup-db 2>&1 | logger -t saferoute-backup
EOF
chmod 644 /etc/cron.d/saferoute-backup

# ---------------------------------------------------------------------------------------------
log "pm2 as $APP_USER (starts on boot, logs rotate)"
if [ ! -f "/etc/systemd/system/pm2-$APP_USER.service" ]; then
  env PATH="$PATH:/usr/bin" pm2 startup systemd -u "$APP_USER" --hp "/home/$APP_USER" >/dev/null
fi
systemctl enable "pm2-$APP_USER" >/dev/null 2>&1 || true
cat > /etc/logrotate.d/pm2-saferoute <<EOF
/home/$APP_USER/.pm2/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su $APP_USER $APP_USER
}
EOF

# ---------------------------------------------------------------------------------------------
log "nginx"
install -d -m 755 /var/www/certbot /var/www/saferoute
install -m 644 "$SRC_DIR/nginx/maintenance.html" /var/www/saferoute/maintenance.html
install -m 644 "$SRC_DIR/nginx/00-defaults.conf" /etc/nginx/conf.d/00-defaults.conf
rm -f /etc/nginx/sites-enabled/default

render_site() { sed "s/__DOMAIN__/$DOMAIN/g" "$SRC_DIR/nginx/$1" > /etc/nginx/sites-available/saferoute.conf; }
CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"

if [ -s "$CERT" ]; then
  render_site site-https.conf.tpl
else
  render_site site-http.conf.tpl
fi
ln -sf /etc/nginx/sites-available/saferoute.conf /etc/nginx/sites-enabled/saferoute.conf
nginx -t
systemctl enable nginx >/dev/null
systemctl reload nginx 2>/dev/null || systemctl restart nginx

# ---------------------------------------------------------------------------------------------
# Firewall before TLS: Let's Encrypt needs 80 open. SSH is allowed first so enabling can't lock us out.
log "Firewall (ufw) and fail2ban"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp >/dev/null
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null

cat > /etc/fail2ban/jail.d/sshd.local <<'EOF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
bantime = 1h
EOF
systemctl enable fail2ban >/dev/null 2>&1
systemctl restart fail2ban

# ---------------------------------------------------------------------------------------------
if [ -z "${SKIP_TLS:-}" ] && [ ! -s "$CERT" ]; then
  log "TLS certificate for $DOMAIN (Let's Encrypt, webroot)"
  if certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
       --non-interactive --agree-tos --register-unsafely-without-email \
       --deploy-hook "systemctl reload nginx"; then
    render_site site-https.conf.tpl
    nginx -t
    systemctl reload nginx
  else
    warn "Certificate issuance failed; staying on HTTP. Check DNS for $DOMAIN and that port 80 is reachable, then re-run."
  fi
fi

log "Done"
echo "Domain:        $DOMAIN  ($( [ -s "$CERT" ] && echo 'HTTPS enabled' || echo 'HTTP only' ))"
echo "App user:      $APP_USER   App dir: $APP_DIR"
echo "Database:      $DB_NAME (role $DB_USER, local only)   Env file: $ENV_FILE"
echo "Node:          $(node -v)   pm2: $(node -p "require(\"/usr/lib/node_modules/pm2/package.json\").version")   nginx: $(nginx -v 2>&1 | cut -d/ -f2)   $(psql --version)"
