#!/usr/bin/env bash
# Nightly SQLite backup: tarball the DB file, keep the last $KEEP.
# Install on the VPS crontab:  @daily /opt/linkshort/scripts/backup.sh
set -euo pipefail

DATA_DIR="${DATA_DIR:-/opt/linkshort/data}"
BACKUP_DIR="${BACKUP_DIR:-/opt/linkshort/backups}"
KEEP="${KEEP:-7}"

mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/links-$(date +%F).tar.gz" -C "$DATA_DIR" links.db
find "$BACKUP_DIR" -name 'links-*.tar.gz' -mtime +"$KEEP" -delete
echo "backup ok: $BACKUP_DIR/links-$(date +%F).tar.gz"
