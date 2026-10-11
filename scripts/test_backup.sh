#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
# Exercise encrypted backup and restore in an isolated container. Transport is
# replaced by a local copy; no keys, hosts or data from an installation are used.
set -euo pipefail
fixture="$(mktemp -d)"
trap 'rm -rf "$fixture"' EXIT
script_dir="$(cd "$(dirname "$0")" && pwd)"
python3 - "$fixture/live.db" <<'PY'
import sqlite3
import sys
from contextlib import closing
with closing(sqlite3.connect(sys.argv[1])) as db, db:
    db.execute('CREATE TABLE samples (download_mbps REAL)')
    db.execute('INSERT INTO samples VALUES (900)')
PY
age-keygen -o "$fixture/identity.txt" 2>/dev/null
recipient="$(age-keygen -y "$fixture/identity.txt")"
mkdir "$fixture/bin"
cat > "$fixture/bin/scp" <<'MOCK'
#!/bin/sh
while [ "$1" != "--" ]; do shift; done
shift
cp "$1" "$TEST_UPLOAD"
MOCK
chmod 0755 "$fixture/bin/scp"
export PATH="$fixture/bin:$PATH" DB_PATH="$fixture/live.db" BACKUP_DIR="$fixture/backups"
export BACKUP_REMOTE='backup.example.com:/archive/' BACKUP_AGE_RECIPIENT="$recipient"
export TEST_UPLOAD="$fixture/upload.age" RETENTION_DAYS=30
bash "$script_dir/backup.sh"
age --decrypt -i "$fixture/identity.txt" -o "$fixture/restored.db" "$TEST_UPLOAD"
python3 - "$fixture/restored.db" <<'PY'
import sqlite3
import sys
from contextlib import closing
with closing(sqlite3.connect(sys.argv[1])) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert db.execute('SELECT download_mbps FROM samples').fetchone()[0] == 900
PY
# Failed off-host transport must fail the backup job, never report success.
printf '#!/bin/sh\nexit 1\n' > "$fixture/bin/scp"
if bash "$script_dir/backup.sh"; then
  echo 'Backup incorrectly accepted a failed transport' >&2
  exit 1
fi
echo 'backup-encryption-restore-ok; transport failure propagated'
