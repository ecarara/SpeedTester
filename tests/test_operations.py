# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise backup/restore and startup validation with isolated databases."""
from contextlib import closing
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from api.store import Sample, SampleStore
from shared.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('restore_script', ROOT / 'scripts/restore.py')
restore_script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore_script)


class OperationsTests(unittest.TestCase):
    def test_live_backup_restores_history_and_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / 'live.db'
            store = SampleStore(str(database))
            store.add_sample(Sample('2026-10-10T12:00:00Z', download_mbps=900))
            environment = {**os.environ, 'DB_PATH':str(database), 'BACKUP_DIR':str(base / 'backups'),
                           'BACKUP_REMOTE':'', 'RETENTION_DAYS':'30'}
            subprocess.run(['bash', str(ROOT / 'scripts/backup.sh')], env=environment, check=True, capture_output=True)
            backup = next((base / 'backups').glob('*.db'))
            store.add_sample(Sample('2026-10-10T13:00:00Z', download_mbps=800))
            store.close()
            restore_script.restore(backup, database)
            restored = SampleStore(str(database))
            self.assertEqual(restored.count(), 1)
            restored.close()
            previous = next(base.glob('live.db.before-restore-*'))
            with closing(sqlite3.connect(previous)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM samples').fetchone()[0], 2)

    def test_invalid_backup_leaves_destination_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database, invalid = base / 'live.db', base / 'invalid.db'
            store = SampleStore(str(database)); store.add_sample(Sample('2026-10-10T12:00:00Z')); store.close()
            original = database.read_bytes()
            invalid.write_text('not a database')
            with self.assertRaises(sqlite3.DatabaseError):
                restore_script.restore(invalid, database)
            self.assertEqual(database.read_bytes(), original)
            self.assertEqual(list(base.glob('.speedtester-restore-*')), [])

    def test_restore_refuses_active_wal_and_same_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            database = base / 'live.db'
            store = SampleStore(str(database)); store.close()
            sidecar = Path(str(database) + '-wal'); sidecar.touch()
            with self.assertRaisesRegex(ValueError, 'sidecars'):
                restore_script.restore(base / 'backup.db', database)
            with self.assertRaisesRegex(ValueError, 'differ'):
                restore_script.restore(database, database)

    def test_invalid_startup_values_fail_instead_of_silent_defaults(self):
        for key, value in [('API_PORT','70000'), ('ANOMALY_RETRY_RATIO','0'),
                           ('MEASUREMENTS_PER_QUADRANT','0'), ('SLOT_LEASE_SECONDS','10'),
                           ('API_REQUIRE_ADMIN_TOKEN','maybe'), ('BANDWIDTH_CONTRACTED_MBP','nan'),
                           ('ISP_LOOKUP_TIMEOUT_SECONDS','-1'), ('TZ','invalid/timezone')]:
            with self.subTest(key=key), patch.dict(os.environ, {key:value}, clear=True):
                with self.assertRaises((ValueError, KeyError)):
                    load_settings()
