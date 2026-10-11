# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

import tempfile
import unittest
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.store import MeasurementSlot, Sample, SampleStore
from collector.anomaly import is_anomalous_download
from collector.collector import Collector
from collector.connectivity import ConnectivitySnapshot
from collector.iperf3_runner import Iperf3Timeout
from collector.quadrants import plan_day_slots


class SchedulerTests(unittest.TestCase):
    def test_anomalous_first_result_is_not_persisted(self):
        settings = SimpleNamespace(
            sample_duration_seconds=30,
            speedtest_server_ids=None,
            max_bytes=10_000_000,
            bandwidth_contracted_mbps=1000,
            isp_lookup_enabled=False,
            isp_lookup_timeout_seconds=1,
            anomaly_retry_ratio=0.5,
            anomaly_retry_min_download_mbps=None,
            speedtest_runner="fast",
            ookla_binary="speedtest",
            iperf3_server=None,
            iperf3_port=5201,
            iperf3_duration_seconds=10,
            iperf3_parallel_streams=5,
            measurement_timeout_seconds=60,
        )
        stored = []
        store = SimpleNamespace(add_sample=stored.append)
        first = SimpleNamespace(
            download_mbps=100,
            upload_mbps=100,
            ping_ms=5,
            jitter_ms=1,
            server_id=None,
            server_name="test",
            server_location=None,
            country=None,
            interface="eth0",
            isp=None,
            bandwidth_contracted_mbps=1000,
            duration_sec=30,
        )
        second = SimpleNamespace(**{**first.__dict__, "download_mbps": 900})
        snapshot = ConnectivitySnapshot(
            gateway="192.0.2.1",
            gateway_reachable=True,
            external_reachable=True,
            evidence={"test": True},
        )
        slot = {"id": 1, "local_date": "2026-08-26", "quadrant": "manha"}

        with patch("collector.collector.probe_connectivity", return_value=snapshot), \
             patch("collector.collector.run_named_runner", side_effect=[first, second]) as run:
            result = Collector(settings, store)._run_single(slot)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(stored), 1)
        self.assertEqual(result.download_mbps, 900)
        self.assertEqual(stored[0].download_mbps, 900)

    def test_iperf3_timeout_is_retried_as_a_fresh_first_attempt(self):
        settings = SimpleNamespace(
            sample_duration_seconds=30,
            speedtest_server_ids=None,
            max_bytes=10_000_000,
            bandwidth_contracted_mbps=1000,
            isp_lookup_enabled=False,
            isp_lookup_timeout_seconds=1,
            anomaly_retry_ratio=0.5,
            anomaly_retry_min_download_mbps=None,
            speedtest_runner="iperf3",
            ookla_binary="speedtest",
            iperf3_server="example",
            iperf3_port=5201,
            iperf3_duration_seconds=10,
            iperf3_parallel_streams=5,
            measurement_timeout_seconds=60,
        )
        stored = []
        store = SimpleNamespace(
            add_sample=stored.append,
            consecutive_external_failure_count=lambda runner: 2,
        )
        result = SimpleNamespace(
            download_mbps=900,
            upload_mbps=500,
            ping_ms=5,
            jitter_ms=1,
            server_id=None,
            server_name="iperf3:example:5201",
            server_location=None,
            country=None,
            interface="eth0",
            isp=None,
            bandwidth_contracted_mbps=1000,
            duration_sec=28,
        )
        snapshot = ConnectivitySnapshot(
            gateway="192.0.2.1",
            gateway_reachable=True,
            external_reachable=True,
            evidence={"test": True},
        )
        slot = {"id": 1, "local_date": "2026-08-26", "quadrant": "manha"}

        with patch("collector.collector.probe_connectivity", return_value=snapshot), \
             patch(
                 "collector.collector.run_named_runner",
                 side_effect=[Iperf3Timeout("60 segundos"), result],
             ) as run:
            saved = Collector(settings, store)._run_single(slot)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(len(stored), 1)
        self.assertEqual(saved.download_mbps, 900)

    def test_timeout_after_external_connectivity_loss_is_operator_failure(self):
        settings = SimpleNamespace(
            sample_duration_seconds=30,
            speedtest_server_ids=None,
            max_bytes=10_000_000,
            bandwidth_contracted_mbps=1000,
            isp_lookup_enabled=False,
            isp_lookup_timeout_seconds=1,
            anomaly_retry_ratio=0.5,
            anomaly_retry_min_download_mbps=None,
            speedtest_runner="iperf3",
            ookla_binary="speedtest",
            iperf3_server="example",
            iperf3_port=5201,
            iperf3_duration_seconds=10,
            iperf3_parallel_streams=5,
            measurement_timeout_seconds=60,
        )
        stored = []
        store = SimpleNamespace(
            add_sample=stored.append,
            consecutive_external_failure_count=lambda runner: 2,
        )
        initial = ConnectivitySnapshot(
            gateway="192.0.2.1",
            gateway_reachable=True,
            external_reachable=True,
            evidence={"initial": True},
        )
        outage = ConnectivitySnapshot(
            gateway="192.0.2.1",
            gateway_reachable=True,
            external_reachable=False,
            evidence={"external": {"example.com": {"reachable": False}}},
        )
        slot = {"id": 1, "local_date": "2026-08-26", "quadrant": "manha"}

        with patch(
            "collector.collector.probe_connectivity",
            side_effect=[initial, outage],
        ), patch(
            "collector.collector.run_named_runner",
            side_effect=Iperf3Timeout("60 segundos"),
        ) as run:
            saved = Collector(settings, store)._run_single(slot)

        self.assertEqual(run.call_count, 1)
        self.assertEqual(len(stored), 1)
        self.assertTrue(saved.is_failure)
        self.assertEqual(saved.failure_cause, "external_timeout")
        self.assertEqual(saved.failure_origin, "OPERATOR")
        self.assertEqual(saved.classification_confidence, "high")

    def test_first_external_timeout_is_not_yet_operator_failure(self):
        self.assertEqual(Collector._external_failure_classification(1), ("UNKNOWN", "low"))
        self.assertEqual(Collector._external_failure_classification(2), ("UNKNOWN", "low"))
        self.assertEqual(Collector._external_failure_classification(3), ("OPERATOR", "high"))

    def test_anomalous_first_result_is_retried_using_contract_threshold(self):
        self.assertTrue(is_anomalous_download(499.9, 1000, 0.5, None))
        self.assertFalse(is_anomalous_download(500, 1000, 0.5, None))

    def test_anomaly_can_use_absolute_threshold_without_contract(self):
        self.assertTrue(is_anomalous_download(99, None, 0.5, 100))
        self.assertFalse(is_anomalous_download(100, None, 0.5, 100))

    def test_anomaly_is_disabled_without_a_valid_threshold(self):
        self.assertFalse(is_anomalous_download(1, None, 0.5, None))
        self.assertFalse(is_anomalous_download(1, 1000, 0, None))

    def test_plan_is_deterministic_and_has_two_slots_per_quadrant(self):
        first = plan_day_slots(date(2026, 8, 26), "America/Sao_Paulo")
        second = plan_day_slots(date(2026, 8, 26), "America/Sao_Paulo")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        self.assertEqual(
            Counter(slot.quadrant for slot in first),
            {"madrugada": 2, "manha": 2, "tarde": 2, "noite": 2},
        )

    def test_slots_are_idempotent_and_power_event_reconciles_them(self):
        planned = plan_day_slots(date(2026, 8, 26), "America/Sao_Paulo")
        with tempfile.TemporaryDirectory() as directory:
            store = SampleStore(str(Path(directory) / "speedtester.db"))
            self.addCleanup(store.close)
            slots = [
                MeasurementSlot(
                    local_date=item.local_date,
                    quadrant=item.quadrant,
                    slot_index=item.slot_index,
                    scheduled_for=item.scheduled_for,
                    schedule_seed=item.schedule_seed,
                )
                for item in planned
            ]

            self.assertEqual(store.add_slots(slots), 8)
            self.assertEqual(store.add_slots(slots), 0)
            event_id = store.add_availability_event(
                "2026-08-26T00:00:00Z",
                "2026-08-27T00:00:00Z",
                "POWER_OUTAGE",
                "manual",
                "high",
                "test outage",
            )

            self.assertGreater(event_id, 0)
            self.assertTrue(
                all(
                    row["status"] == "POWER_OUTAGE"
                    for row in store.slots_for_date("2026-08-26")
                )
            )
            row = store.slots_for_date("2026-08-26")[0]
            self.assertTrue(store.classify_slot(row["id"], "NO_INTERNET_OPERATOR", "Modem ligado, sem acesso externo"))
            classified = store.slots_for_date("2026-08-26")[0]
            self.assertEqual(classified["status"], "NO_INTERNET_OPERATOR")
            self.assertEqual(classified["classification_source"], "manual")
            self.assertEqual(classified["classification_note"], "Modem ligado, sem acesso externo")
            store.add_sample(
                Sample(
                    started_at="2026-08-26T12:00:00Z",
                    slot_id=row["id"],
                    local_date=row["local_date"],
                    quadrant=row["quadrant"],
                    download_mbps=10,
                    upload_mbps=2,
                )
            )
            self.assertEqual(store.all_samples()[0]["slot_id"], row["id"])

    def test_heartbeat_and_alerts_are_persisted_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SampleStore(str(Path(directory) / "speedtester.db"))
            self.addCleanup(store.close)
            store.record_heartbeat("collector", "idle", {"runner": "iperf3"})
            heartbeat = store.latest_heartbeat("collector")
            self.assertEqual(heartbeat["status"], "idle")
            self.assertEqual(heartbeat["metadata"]["runner"], "iperf3")

            first = store.add_alert("speed_degraded", "Download abaixo do contrato", cooldown_seconds=3600)
            duplicate = store.add_alert("speed_degraded", "Outro aviso", cooldown_seconds=3600)
            self.assertIsNotNone(first)
            self.assertIsNone(duplicate)
            self.assertEqual(len(store.alerts()), 1)
            store.mark_alert_delivery(first, True)
            self.assertEqual(store.alerts()[0]["delivered"], 1)


if __name__ == "__main__":
    unittest.main()
