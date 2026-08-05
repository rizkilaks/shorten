#!/usr/bin/env bash
# Nightly SQLite backup: consistent snapshot via sqlite3 .backup, keep the last $KEEP.
# Requires: sqlite3 (on Debian/Ubuntu: apt install sqlite3).
# Install on the VPS crontab:  @daily /opt/linkshort/scripts/backup.sh
set -euo pipefail

DATA_DIR="${DATA_DIR:-/opt/linkshort/app/data}"
BACKUP_DIR="${BACKUP_DIR:-/opt/linkshort/app/backups}"
KEEP="${KEEP:-7}"

mkdir -p "$BACKUP_DIR"

SNAPSHOT="$BACKUP_DIR/links-$(date +%F).tar.gz"
TMP_DB="$BACKUP_DIR/links.snapshot.db"

sqlite3 "$DATA_DIR/links.db" ".backup '$TMP_DB'"
tar -czf "$SNAPSHOT" -C "$BACKUP_DIR" links.snapshot.db
rm -f "$TMP_DB"

find "$BACKUP_DIR" -name 'links-*.tar.gz' -mtime +"$KEEP" -delete
echo "backup ok: $SNAPSHOT"
