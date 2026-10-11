# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Deterministic regression tests for API, restart recovery and audit evidence."""
import json
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from api.store import DB_SCHEMA, MeasurementSlot, Sample, SampleStore
from collector.collector import Collector
from collector.connectivity import ConnectivitySnapshot, probe_connectivity

with tempfile.TemporaryDirectory() as initial:
    with patch.dict(os.environ, {"DB_PATH": str(Path(initial) / 'bootstrap.db'), "MPLCONFIGDIR": str(Path(initial) / 'mpl')}):
        from api import server
        server.store.close()


class IntegrationFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'test.db')
        self.store = SampleStore(self.path)
        self.addCleanup(self.store.close)
        self.settings = replace(server.settings, api_require_login=False, api_admin_token='integration-test', api_rate_limit_per_minute=100_000)
        self.store_patch = patch.object(server, 'store', self.store)
        self.settings_patch = patch.object(server, 'settings', self.settings)
        self.store_patch.start(); self.settings_patch.start()
        self.addCleanup(self.store_patch.stop); self.addCleanup(self.settings_patch.stop)
        self.client = TestClient(server.app)
        self.addCleanup(self.client.close)

    def add_many(self, count=1007):
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        self.store.add_samples(Sample(started_at=(start + timedelta(minutes=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            runner='fast' if i < 1000 else 'iperf3', download_mbps=900, upload_mbps=450,
            local_date='2026-10-01', quadrant='manha') for i in range(count))

    def slot(self, when='2026-10-11T12:00:00Z'):
        self.store.add_slots([MeasurementSlot('2026-10-11', 'manha', 1, when, 'test')])
        return self.store.all_slots()[0]

