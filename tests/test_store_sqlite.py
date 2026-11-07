# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""SQLite connection reuse, WAL and busy-timeout contracts."""
import tempfile
import threading
import unittest
from pathlib import Path

from api.store import SampleStore


class StoreSQLiteTests(unittest.TestCase):
    def test_wal_busy_timeout_and_connection_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SampleStore(str(Path(directory) / "speedtester.db"))
            try:
                with store._connection() as conn:
                    self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
                    self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
                connection = store._connect()
                with store._connection() as conn:
                    self.assertIs(store._connect(), connection)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 0)
            finally:
                store.close()

    def test_parallel_readers_do_not_share_a_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SampleStore(str(Path(directory) / "speedtester.db"))
            barrier = threading.Barrier(4)
            errors = []
            def reader():
                try:
                    barrier.wait(5)
                    with store._connection() as conn:
                        conn.execute("SELECT COUNT(*) FROM samples").fetchone()
                except Exception as exc:  # pragma: no cover - failure evidence
                    errors.append(exc)
            threads = [threading.Thread(target=reader) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
            store.close()
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
