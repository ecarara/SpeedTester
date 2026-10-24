# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Contract validation and auditable single-retry behavior for all runners."""
from dataclasses import replace
import os
from pathlib import Path
import sqlite3
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from fixtures import IntegrationFixture, server
from api.store import DB_SCHEMA, SampleStore
from collector.anomaly import anomalous_directions
from collector.collector import Collector
from collector.connectivity import ConnectivitySnapshot
from shared.settings import load_settings


class ContractAnomalyTests(IntegrationFixture):
    def configured_settings(self, **values):
        config = Path(self.tmp.name) / "contract.env"
        config.write_text("TZ=UTC\nBANDWIDTH_CONTRACTED_MBP=1000\nBANDWIDTH_CONTRACTED_UPLOAD_MBPS=500\n")
        if os.name != "nt":
            # Exercise the same file-writing path shipped in the packages.
            config.unlink()
            root = Path(__file__).resolve().parents[1]
            environment = dict(os.environ, SPEEDTESTER_CONFIG_DIR=self.tmp.name, SPEEDTESTER_ENV_FILE=str(config),
                SPEEDTESTER_NONINTERACTIVE="1", SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS="1000",
                SPEEDTESTER_CONTRACTED_UPLOAD_MBPS="500", SPEEDTESTER_CONFIRM_EXISTING="1")
            subprocess.run(["bash", str(root / "packaging/linux/configure-user.sh")],
                           env=environment, capture_output=True, text=True, check=True, timeout=10)
        with patch.dict(os.environ, {"SPEEDTESTER_CONFIG_FILE": str(config)}, clear=True):
            settings = load_settings()
        self.assertEqual((settings.bandwidth_contracted_mbps, settings.bandwidth_contracted_upload_mbps), (1000, 500))
        return replace(settings, isp_lookup_enabled=False, **values)

    @staticmethod
    def result(download, upload):
        return SimpleNamespace(download_mbps=download, upload_mbps=upload, ping_ms=5, jitter_ms=1,
            server_id=None, server_name="fixture", server_location=None, country=None,
            interface="fixture", isp=None, bandwidth_contracted_mbps=1000, duration_sec=20)

    def measure(self, settings, first, second):
        slot = self.slot()
        self.store.claim_slot(slot["id"])
        snapshot = ConnectivitySnapshot("192.0.2.1", True, True, {"fixture": True})
        with patch("collector.collector.probe_connectivity", return_value=snapshot), \
                patch("collector.collector.run_named_runner", side_effect=[first, second]) as runner:
            saved = Collector(settings, self.store)._run_single(slot)
        return saved, runner, slot

    def test_reported_367_220_case_retries_for_every_runner_and_keeps_one_sample(self):
        for name in ("iperf3", "ookla", "fast"):
            with self.subTest(runner=name):
                self.store.reset()
                settings = self.configured_settings(speedtest_runner=name)
                saved, runner, slot = self.measure(settings, self.result(367, 220), self.result(930, 490))
                self.assertEqual(runner.call_count, 2)
                self.assertEqual([c.args[0] for c in runner.call_args_list], [name, name])
                self.assertEqual(self.store.count(), 1)
                self.assertEqual((saved.download_mbps, saved.upload_mbps), (930, 490))
                self.assertEqual(saved.bandwidth_contracted_upload_mbps, 500)
                row = self.store.all_samples()[0]
                self.assertEqual(row["bandwidth_contracted_upload_mbps"], 500)
                attempts = self.store.attempts_for_slot(slot["id"])
                self.assertEqual([a["outcome"] for a in attempts], ["discarded", "selected"])
                self.assertIn("download, upload", attempts[0]["reason"])
                self.assertEqual(attempts[0]["metrics"]["download_mbps"], 367)
                self.assertEqual(attempts[0]["metrics"]["bandwidth_contracted_upload_mbps"], 500)

    def test_upload_alone_triggers_retry(self):
        saved, runner, slot = self.measure(self.configured_settings(), self.result(930, 220), self.result(900, 450))
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(saved.upload_mbps, 450)
        self.assertIn("upload", self.store.attempts_for_slot(slot["id"])[0]["reason"])

    def test_second_low_result_remains_representative_without_selecting_highest(self):
        saved, runner, slot = self.measure(self.configured_settings(), self.result(367, 220), self.result(300, 180))
        self.assertEqual(runner.call_count, 2)
        self.assertEqual((saved.download_mbps, saved.upload_mbps), (300, 180))
        self.assertEqual(len(self.store.attempts_for_slot(slot["id"])), 2)
        self.assertEqual(self.store.count(), 1)

    def test_failed_retry_does_not_restore_the_discarded_first_measurement(self):
        saved, runner, slot = self.measure(self.configured_settings(), self.result(367, 220),
                                           RuntimeError("synthetic measurement server failure"))
        self.assertEqual(runner.call_count, 2)
        self.assertTrue(saved.is_failure)
        self.assertIsNone(saved.download_mbps)
        self.assertEqual([a["outcome"] for a in self.store.attempts_for_slot(slot["id"])],
                         ["discarded", "error"])
        self.assertEqual(self.store.count(), 1)

    def test_boundaries_and_absent_contract_do_not_trigger_false_retries(self):
        self.assertEqual(anomalous_directions(500, 250, 1000, 500, 0.5), [])
        self.assertEqual(anomalous_directions(499.9, 250, 1000, 500, 0.5), ["download"])
        self.assertEqual(anomalous_directions(500, 249.9, 1000, 500, 0.5), ["upload"])
        self.assertEqual(anomalous_directions(1, 1, None, None, 0.5), [])
        self.assertEqual(anomalous_directions(99, 1, None, None, 0.5, 100), ["download"])

    def test_api_exposes_contract_and_effective_retry_policy(self):
        with patch.object(server, "settings", replace(self.configured_settings(), api_require_login=False)):
            data = self.client.get("/api/config").json()
        self.assertEqual(data["bandwidth_contracted_mbps"], 1000)
        self.assertEqual(data["bandwidth_contracted_upload_mbps"], 500)
        self.assertEqual(data["anomaly_retry_ratio"], 0.5)

    def test_invalid_contract_values_fail_settings_validation(self):
        for value in ("0", "-1", "nan", "inf", "1e309"):
            with self.subTest(value=value), patch.dict(os.environ, {
                "SPEEDTESTER_CONFIG_FILE": str(Path(self.tmp.name) / "missing.env"),
                "BANDWIDTH_CONTRACTED_UPLOAD_MBPS": value}, clear=True):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_schema_10_migration_preserves_history_and_adds_nullable_upload_contract(self):
        path = str(Path(self.tmp.name) / "old.db")
        with sqlite3.connect(path) as conn:
            conn.executescript(DB_SCHEMA.replace("    bandwidth_contracted_upload_mbps REAL,\n", ""))
            conn.execute("INSERT INTO samples(id, started_at, download_mbps, bandwidth_contracted_mbps) "
                         "VALUES (1, '2026-10-01T00:00:00Z', 930, 1000)")
        for _ in range(2):
            store = SampleStore(path)
            try:
                row = store.all_samples()[0]
                self.assertEqual(row["download_mbps"], 930)
                self.assertEqual(row["bandwidth_contracted_mbps"], 1000)
                self.assertIsNone(row["bandwidth_contracted_upload_mbps"])
            finally:
                store.close()
