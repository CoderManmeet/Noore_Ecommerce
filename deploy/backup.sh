#!/usr/bin/env bash
# Nightly backup: the PostgreSQL database and the uploaded media, kept for BACKUP_KEEP_DAYS,
# copied off-site when BACKUP_REMOTE is set.
#
# Reads DATABASE_URL (from backend/.env) and the values in deploy/backup.env.
# Exits non-zero on any failure, so systemd records the run as failed.
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is not set}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/noore}"
MEDIA_DIR="${MEDIA_DIR:-/srv/noore/backend/media}"
BACKUP_KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
BACKUP_REMOTE="${BACKUP_REMOTE:-}"

stamp="$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"
umask 077

db_file="$BACKUP_DIR/db-$stamp.dump"
media_file="$BACKUP_DIR/media-$stamp.tar.gz"

# Custom format: compressed, and restorable table by table with pg_restore.
pg_dump --format=custom --no-owner --no-privileges --file="$db_file.partial" "$DATABASE_URL"
mv "$db_file.partial" "$db_file"

if [ -d "$MEDIA_DIR" ]; then
    tar -czf "$media_file.partial" -C "$(dirname "$MEDIA_DIR")" "$(basename "$MEDIA_DIR")"
    mv "$media_file.partial" "$media_file"
fi

# A dump that pg_restore cannot even list is not a backup.
pg_restore --list "$db_file" > /dev/null

# Keep the last BACKUP_KEEP_DAYS days locally.
find "$BACKUP_DIR" -maxdepth 1 -type f \( -name 'db-*.dump' -o -name 'media-*.tar.gz' \) -mtime "+$BACKUP_KEEP_DAYS" -delete

if [ -n "$BACKUP_REMOTE" ]; then
    rclone copy "$BACKUP_DIR" "$BACKUP_REMOTE" --include 'db-*.dump' --include 'media-*.tar.gz' --max-age "${BACKUP_KEEP_DAYS}d"
    rclone delete "$BACKUP_REMOTE" --min-age "${BACKUP_KEEP_DAYS}d" --include 'db-*.dump' --include 'media-*.tar.gz'
    echo "backup $stamp written and copied to $BACKUP_REMOTE"
else
    echo "backup $stamp written to $BACKUP_DIR (NOT copied off-site: BACKUP_REMOTE is not set)"
fi
