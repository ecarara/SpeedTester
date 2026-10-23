# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Destination failures stay auditable without becoming operator outages."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from fixtures import IntegrationFixture
from collector.collector import Collector
from collector.connectivity import ConnectivitySnapshot
from collector.iperf3_runner import Iperf3TargetUnavailable


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
