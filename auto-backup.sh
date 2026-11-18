#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

MODE="${1:-daily}"
ROOT="${BACKUP_ROOT:-/srv/backups}"
WEB="${BACKUP_WEB:-/var/www}"
CNF="${BACKUP_DB_CNF:-/etc/mysql/backup-client.cnf}"
DUMP_BIN="${BACKUP_DUMP_BIN:-mariadb-dump}"
TODAY=$(date +%F)
WEEK=$(date +%G-W%V)

mkdir -p "$ROOT/daily" "$ROOT/weekly"
exec 9>"$ROOT/.backup.lock"
flock -n 9 || { echo 'Another backup is running' >&2; exit 1; }
log() { printf '[%s] %s\n' "$(date -Is)" "$*" | tee -a "$ROOT/backup.log"; }

if [[ "$MODE" == daily ]]; then
  [[ -d "$WEB" && -r "$CNF" ]] || { log 'Missing application directory or DB credentials'; exit 1; }
  command -v "$DUMP_BIN" >/dev/null || { log "Missing dump command: $DUMP_BIN"; exit 1; }
  DEST="$ROOT/daily/$TODAY"
  [[ ! -e "$DEST" ]] || { log "Backup already exists: $DEST"; exit 0; }
  TMP=$(mktemp -d "$ROOT/daily/.tmp.XXXXXXXX")
  trap 'rm -rf -- "$TMP"' EXIT
  log 'Starting daily backup'
  tar -czf "$TMP/apps.tar.gz" -C "$WEB" .
  "$DUMP_BIN" --defaults-extra-file="$CNF" --all-databases \
    --single-transaction --quick --routines --events --triggers \
    | gzip > "$TMP/databases.sql.gz"
  tar -tzf "$TMP/apps.tar.gz" >/dev/null
  gzip -t "$TMP/databases.sql.gz"
  [[ -s "$TMP/databases.sql.gz" ]] || { log 'Database archive is empty'; exit 1; }
  mv -- "$TMP" "$DEST"
  trap - EXIT
  find "$ROOT/daily" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??' -mtime +7 -exec rm -rf -- {} +
  log "Daily backup complete: $DEST"
elif [[ "$MODE" == weekly ]]; then
  SRC="$ROOT/daily/$TODAY"
  DEST="$ROOT/weekly/$WEEK"
  [[ -f "$SRC/apps.tar.gz" && -f "$SRC/databases.sql.gz" ]] || { log "Missing daily archive: $SRC"; exit 1; }
  [[ ! -e "$DEST" ]] || { log "Weekly backup already exists: $DEST"; exit 0; }
  TMP=$(mktemp -d "$ROOT/weekly/.tmp.XXXXXXXX")
  trap 'rm -rf -- "$TMP"' EXIT
  cp -a -- "$SRC/." "$TMP/"
  tar -tzf "$TMP/apps.tar.gz" >/dev/null
  gzip -t "$TMP/databases.sql.gz"
  mv -- "$TMP" "$DEST"
  trap - EXIT
  find "$ROOT/weekly" -mindepth 1 -maxdepth 1 -type d -name '????-W??' -mtime +56 -exec rm -rf -- {} +
  log "Weekly backup complete: $DEST"
else
  echo 'Usage: auto-backup.sh [daily|weekly]' >&2
  exit 2
fi
