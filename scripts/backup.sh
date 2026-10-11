#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# Create a consistent SQLite backup without stopping the collector.
set -euo pipefail

DB_PATH="${DB_PATH:-/data/speedtester.db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
umask 077
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || { echo "RETENTION_DAYS must be nonnegative" >&2; exit 1; }
mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
destination="$BACKUP_DIR/speedtester-${timestamp}.db"

python3 - "$DB_PATH" "$destination" <<'PY'
import sqlite3
from contextlib import closing
import sys

source, destination = sys.argv[1:]
with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as source_connection:
    with closing(sqlite3.connect(destination)) as destination_connection:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SystemExit(f"Backup integrity check failed: {result}")
print(destination)
PY

# Off-host copies are always age-encrypted. SSH requires a preconfigured key
# and known_hosts; BatchMode prevents unattended password prompts.
if [[ -n "${BACKUP_REMOTE:-}" ]]; then
  : "${BACKUP_AGE_RECIPIENT:?BACKUP_AGE_RECIPIENT is required for remote backup}"
  encrypted="$destination.age"
  age -r "$BACKUP_AGE_RECIPIENT" -o "$encrypted" "$destination"
  scp -B -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -- "$encrypted" "$BACKUP_REMOTE"
fi

# Retain only the requested backup window. The glob is intentionally scoped to
# the backup directory and to files created by this script.
find "$BACKUP_DIR" -type f \( -name 'speedtester-*.db' -o -name 'speedtester-*.db.age' \) -mtime "+$RETENTION_DAYS" -delete
