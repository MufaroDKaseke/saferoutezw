#!/usr/bin/env bash
# Nightly PostgreSQL dump, installed by bootstrap.sh as /usr/local/sbin/saferoute-backup-db.
# Keeps KEEP_DAYS days of custom-format dumps (restore with pg_restore). These live on the same
# disk as the database, so also enable DigitalOcean droplet backups or copy them off-site.
set -euo pipefail

DB_NAME="${DB_NAME:-saferoutezw}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/saferoutezw}"
KEEP_DAYS="${KEEP_DAYS:-14}"

install -d -m 700 -o postgres -g postgres "$BACKUP_DIR"
file="$BACKUP_DIR/${DB_NAME}_$(date -u +%Y%m%dT%H%M%SZ).dump"
runuser -u postgres -- pg_dump --format=custom --file="$file" "$DB_NAME"
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+$KEEP_DAYS" -delete
echo "backup written: $file ($(du -h "$file" | cut -f1))"
