# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Destination failures stay auditable without becoming operator outages."""
import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from fixtures import IntegrationFixture
from collector.collector import Collector
from collector.connectivity import ConnectivitySnapshot
from collector.iperf3_runner import Iperf3TargetUnavailable
from collector.network_metrics import PingMetrics


class TargetEvidenceTests(IntegrationFixture):
    def setUp(self):
        super().setUp()
        self.snapshot = ConnectivitySnapshot("192.0.2.1", True, True, {"external": True})
        self.evidence = [{"server_name": "iperf3:target.example:5201", "outcome": "error",
                          "detail": "Connection refused", "target_selection": "automatic"}]

    def test_failure_persists_destinations_in_attempt_and_sample_without_operator_alert(self):
        slot = self.slot()
        self.store.claim_slot(slot["id"])
        error = Iperf3TargetUnavailable("iperf3 target.example:5201: Connection refused")
        error.target_attempts = self.evidence
        collector = Collector(self.settings, self.store)
        with patch("collector.collector.probe_connectivity", return_value=self.snapshot), \
                patch.object(collector, "_dispatch_speedtest", side_effect=error):
            sample = collector._run_single(slot)
        self.assertEqual(sample.failure_origin, "MEASUREMENT")
        self.assertEqual(sample.failure_cause, "server")
        self.assertIn("target.example:5201", sample.failure_note)
        self.assertIsNone(sample.download_mbps)
        self.assertEqual(json.loads(self.store.all_samples()[0]["evidence_json"])["target_attempts"], self.evidence)
        self.assertEqual(self.store.attempts_for_slot(slot["id"])[0]["metrics"]["target_attempts"], self.evidence)
        self.assertFalse(any(alert["kind"] == "operator_outage" for alert in self.store.alerts()))
        self.assertEqual(self.snapshot.evidence, {"external": True})

    def test_selected_result_keeps_prior_refusal_and_selected_target(self):
        slot = self.slot()
        self.store.claim_slot(slot["id"])
        targets = self.evidence + [{"server_name": "iperf3:next.example:5201", "outcome": "selected"}]
        result = SimpleNamespace(download_mbps=900, upload_mbps=500, ping_ms=5, jitter_ms=1,
            server_id=None, server_name="iperf3:next.example:5201", server_location="fixture",
            country=None, interface="fixture", isp=None, bandwidth_contracted_mbps=1000,
            duration_sec=20, target_attempts=targets)
        collector = Collector(self.settings, self.store)
        with patch("collector.collector.probe_connectivity", return_value=self.snapshot), \
                patch.object(collector, "_dispatch_speedtest", return_value=result):
            sample = collector._run_single(slot)
        self.assertFalse(sample.is_failure)
        self.assertEqual(sample.server_name, "iperf3:next.example:5201")
        self.assertEqual(json.loads(sample.evidence_json)["target_attempts"], targets)
        attempt = self.store.attempts_for_slot(slot["id"])[0]
        self.assertEqual(attempt["outcome"], "selected")
        self.assertEqual(attempt["metrics"]["target_attempts"], targets)
        self.assertEqual(self.snapshot.evidence, {"external": True})

    def test_real_dispatch_recovers_download_refusal_and_persists_complete_pair(self):
        slot = self.slot()
        self.store.claim_slot(slot["id"])
        settings = replace(self.settings, speedtest_runner="iperf3", iperf3_server=None,
                           iperf3_location={"latitude": -23.55, "longitude": -46.63},
                           isp_lookup_enabled=False, bandwidth_contracted_mbps=None,
                           anomaly_retry_min_download_mbps=None)
        def success(rate, retransmits, transferred):
            summary = {"bits_per_second": rate * 1_000_000, "retransmits": retransmits,
                       "bytes": transferred}
            return subprocess.CompletedProcess([], 0, json.dumps({"end": {
                "sum_sent": summary, "sum_received": summary}}), "")
        results = [success(123, 99, 100), subprocess.CompletedProcess([], 1, json.dumps({
            "error": "unable to connect to server: Connection refused", "system_info": "private-machine"}), ""),
            success(500, 2, 200), success(900, 3, 300)]
        collector = Collector(settings, self.store)
        with patch("collector.collector.probe_connectivity", return_value=self.snapshot), \
                patch("collector.iperf3_runner.iperf_binary", return_value="fixture-iperf"), \
                patch("collector.iperf3_runner.subprocess.run", side_effect=results) as execute, \
                patch("collector.iperf3_runner.measure_ping", return_value=PingMetrics(5, 1, 4, 6, 0)), \
                patch("collector.iperf3_runner._detect_interface", return_value="fixture"):
            sample = collector._run_single(slot)
        self.assertFalse(sample.is_failure)
        self.assertEqual((sample.upload_mbps, sample.download_mbps, sample.tcp_retransmits), (500, 900, 5))
        self.assertEqual(sample.server_name, "iperf3:148.230.60.200:30001")
        self.assertEqual(execute.call_count, 4)
        evidence = json.loads(self.store.all_samples()[0]["evidence_json"])["target_attempts"]
        self.assertEqual([t["outcome"] for t in evidence], ["download_error", "selected"])
        self.assertNotIn("private-machine", json.dumps(evidence))
        attempt = self.store.attempts_for_slot(slot["id"])[0]
        self.assertEqual(attempt["outcome"], "selected")
        self.assertEqual(attempt["metrics"]["target_attempts"], evidence)
        self.assertEqual(attempt["metrics"]["transfer_bytes"], 500)
