#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# Create a consistent SQLite backup without stopping the collector.
set -euo pipefail

DB_PATH="${DB_PATH:-/data/speedtester.db}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
mkdir -p "$BACKUP_DIR"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$BACKUP_DIR/speedtester-${timestamp}.db"

python3 - "$DB_PATH" "$destination" <<'PY'
import sqlite3
import sys

source, destination = sys.argv[1:]
with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_connection:
    with sqlite3.connect(destination) as destination_connection:
        source_connection.backup(destination_connection)
        result = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise SystemExit(f"Backup integrity check failed: {result}")
print(destination)
PY

# Retain only the requested backup window. The glob is intentionally scoped to
# the backup directory and to files created by this script.
find "$BACKUP_DIR" -type f -name 'speedtester-*.db' -mtime "+$RETENTION_DAYS" -delete
