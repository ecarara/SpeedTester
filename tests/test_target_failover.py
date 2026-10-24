# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Geographic recovery with synthetic runners; never contact public targets."""
import json
import subprocess
from dataclasses import replace
import unittest
from unittest.mock import patch

from collector.iperf3_runner import (
    Iperf3TargetUnavailable, Iperf3Timeout, IperfRunMetrics, _run_once_metrics, run_iperf3,
)
from collector.network_metrics import PingMetrics
from collector.target_selection import Target, TargetSelectionError, rank_targets


class TargetRankingTests(unittest.TestCase):
    def test_all_candidates_are_geographic_not_throughput_ranked(self):
        targets = (
            Target("far.example", latitude=40, longitude=0, capacity_gbps=1000),
            Target("near.example", latitude=0, longitude=0, capacity_gbps=1),
            Target("second.example", latitude=1, longitude=0, capacity_gbps=10),
        )
        ranked = rank_targets(location={"latitude": 0, "longitude": 0}, targets=targets)
        self.assertEqual([t.host for t in ranked], ["near.example", "second.example", "far.example"])
        self.assertLess(ranked[1].distance_km, ranked[2].distance_km)

    def test_manual_and_coarse_location_do_not_expand_to_random_hosts(self):
        manual = rank_targets("manual.example", 5300)
        self.assertEqual(len(manual), 1)
        self.assertEqual((manual[0].host, manual[0].port, manual[0].mode), ("manual.example", 5300, "manual"))
        ranked = rank_targets(location={"country_code": "BR", "city": "São Paulo"})
        self.assertTrue(all(t.country_code == "BR" and t.mode == "automatic-city" for t in ranked))
        with self.assertRaises(TargetSelectionError):
            rank_targets(location={})


class GeographicRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.targets = tuple(Target(f"target-{i}.example", distance_km=i) for i in range(1, 5))
        self.options = dict(location={"latitude": 0, "longitude": 0},
                            isp_lookup_enabled=False, binary="fixture-iperf")
        self.metrics = IperfRunMetrics(900, 0, 8192)
        self.now = 0.0
        patches = {
            "rank_targets": dict(return_value=self.targets),
            "_run_once_metrics": dict(return_value=self.metrics),
            "measure_ping": dict(return_value=PingMetrics(5, 1, 4, 6, 0)),
            "resolve_network_identity": dict(side_effect=AssertionError("unexpected external lookup")),
            "_detect_interface": dict(return_value="fixture"),
            "time.monotonic": dict(side_effect=lambda: self.now),
        }
        self.mocks = {}
        for name, options in patches.items():
            patcher = patch("collector.iperf3_runner." + name, **options)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_refused_target_uses_next_for_both_directions(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [Iperf3TargetUnavailable("Connection refused"), self.metrics, self.metrics]
        result = run_iperf3(**self.options)
        self.assertEqual([c.args[1] for c in execute.call_args_list],
                         [self.targets[0].host, self.targets[1].host, self.targets[1].host])
        self.assertEqual([c.kwargs["reverse"] for c in execute.call_args_list], [False, False, True])
        self.assertEqual(result.server_name, "iperf3:target-2.example:5201")
        self.assertEqual([a["outcome"] for a in result.target_attempts], ["error", "selected"])

    def test_refusals_are_bounded_and_keep_every_destination(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = Iperf3TargetUnavailable("Connection refused")
        with self.assertRaises(Iperf3TargetUnavailable) as captured:
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 3)
        self.assertEqual(len(captured.exception.target_attempts), 3)
        self.assertEqual(captured.exception.target_attempts[-1]["server_name"], "iperf3:target-3.example:5201")

    def test_manual_refusal_does_not_use_a_catalog_target(self):
        self.mocks["rank_targets"].return_value = (replace(self.targets[0], mode="manual"),)
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = Iperf3TargetUnavailable("Connection refused")
        with self.assertRaises(Iperf3TargetUnavailable):
            run_iperf3(server="target-1.example", **self.options)
        self.assertEqual(execute.call_count, 1)
        self.mocks["resolve_network_identity"].assert_not_called()

    def test_timeout_retains_its_type_without_trying_a_new_destination(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = Iperf3Timeout("timeout")
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(len(captured.exception.target_attempts), 1)

    def test_invalid_data_does_not_trigger_geographic_recovery(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = RuntimeError("invalid result")
        with self.assertRaisesRegex(RuntimeError, "invalid result"):
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 1)

    def test_download_refusal_restarts_both_directions_on_next_target(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [IperfRunMetrics(123, 99, 100),
                               Iperf3TargetUnavailable("Connection refused"),
                               IperfRunMetrics(500, 2, 200), IperfRunMetrics(900, 3, 300)]
        result = run_iperf3(**self.options)
        self.assertEqual([c.args[1] for c in execute.call_args_list],
                         [t.host for t in (self.targets[0], self.targets[0], self.targets[1], self.targets[1])])
        self.assertEqual([c.kwargs["reverse"] for c in execute.call_args_list], [False, True, False, True])
        self.assertEqual((result.upload_mbps, result.download_mbps, result.tcp_retransmits,
                          result.transfer_bytes), (500, 900, 5, 500))
        self.assertEqual(result.server_name, "iperf3:target-2.example:5201")
        self.assertEqual([a["outcome"] for a in result.target_attempts], ["download_error", "selected"])

    def test_download_busy_also_discards_the_partial_pair(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [self.metrics, Iperf3TargetUnavailable("the server is busy"),
                               self.metrics, self.metrics]
        result = run_iperf3(**self.options)
        self.assertEqual(result.server_name, "iperf3:target-2.example:5201")
        self.assertEqual([a["outcome"] for a in result.target_attempts], ["download_error", "selected"])

    def test_manual_download_refusal_preserves_the_manual_choice(self):
        self.mocks["rank_targets"].return_value = (replace(self.targets[0], mode="manual"),)
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [self.metrics, Iperf3TargetUnavailable("Connection refused")]
        with self.assertRaises(Iperf3TargetUnavailable) as captured:
            run_iperf3(server="target-1.example", **self.options)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(captured.exception.target_attempts[0]["outcome"], "download_error")

    def test_download_timeout_still_requires_connectivity_diagnostics(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [self.metrics, Iperf3Timeout("timeout")]
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(captured.exception.target_attempts[0]["outcome"], "download_error")

    def test_invalid_download_does_not_switch_targets_to_select_another_result(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [self.metrics, RuntimeError("invalid result")]
        with self.assertRaisesRegex(RuntimeError, "invalid result") as captured:
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(captured.exception.target_attempts[0]["outcome"], "download_error")

    def test_upload_and_download_failures_share_the_same_three_target_limit(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [Iperf3TargetUnavailable("Connection refused"), self.metrics,
                               Iperf3TargetUnavailable("server is busy"), self.metrics, self.metrics]
        result = run_iperf3(**self.options)
        self.assertEqual(result.server_name, "iperf3:target-3.example:5201")
        self.assertEqual([a["outcome"] for a in result.target_attempts],
                         ["error", "download_error", "selected"])
        self.assertEqual(execute.call_count, 5)

    def test_repeated_download_refusals_are_bounded_to_three_targets(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [self.metrics, Iperf3TargetUnavailable("Connection refused")] * 3
        with self.assertRaises(Iperf3TargetUnavailable) as captured:
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 6)
        self.assertEqual([a["outcome"] for a in captured.exception.target_attempts], ["download_error"] * 3)
        self.assertEqual([a["server_name"] for a in captured.exception.target_attempts],
                         [f"iperf3:{t.host}:{t.port}" for t in self.targets[:3]])

    def test_download_recovery_uses_only_the_original_remaining_budget(self):
        def execute(_binary, _host, *_args, reverse, **_kwargs):
            self.now += 10
            if self.now == 20:
                raise Iperf3TargetUnavailable("Connection refused")
            return self.metrics
        self.mocks["_run_once_metrics"].side_effect = execute
        result = run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual([c.kwargs["timeout_seconds"] for c in self.mocks["_run_once_metrics"].call_args_list],
                         [60, 50, 40, 30])
        self.assertEqual(result.duration_sec, 40)

    def test_no_new_target_after_download_refusal_exhausts_deadline(self):
        def execute(_binary, _host, *_args, reverse, **_kwargs):
            if reverse:
                self.now = 60
                raise Iperf3TargetUnavailable("Connection refused")
            return self.metrics
        self.mocks["_run_once_metrics"].side_effect = execute
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual(self.mocks["_run_once_metrics"].call_count, 2)
        self.assertEqual(len(captured.exception.target_attempts), 1)
        self.assertEqual(captured.exception.target_attempts[0]["outcome"], "download_error")

    def test_low_speed_never_changes_destination(self):
        self.mocks["_run_once_metrics"].return_value = IperfRunMetrics(10, 0, 8192)
        result = run_iperf3(**self.options)
        self.assertEqual(result.download_mbps, 10)
        self.assertEqual(self.mocks["_run_once_metrics"].call_count, 2)
        self.assertEqual(len(result.target_attempts), 1)

    def test_all_candidates_and_directions_share_the_original_budget(self):
        def execute(_binary, host, *_args, **_kwargs):
            self.now += 5
            if host == self.targets[0].host:
                raise Iperf3TargetUnavailable("Connection refused")
            return self.metrics
        self.mocks["_run_once_metrics"].side_effect = execute
        result = run_iperf3(timeout_seconds=60, **self.options)
        budgets = [c.kwargs["timeout_seconds"] for c in self.mocks["_run_once_metrics"].call_args_list]
        self.assertEqual(budgets, [60, 55, 50])
        self.assertEqual(result.duration_sec, 15)

    def test_no_new_process_is_started_when_the_shared_budget_expires(self):
        def refuse(*_args, **_kwargs):
            self.now = 61
            raise Iperf3TargetUnavailable("Connection refused")
        self.mocks["_run_once_metrics"].side_effect = refuse
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual(self.mocks["_run_once_metrics"].call_count, 1)
        self.assertEqual(len(captured.exception.target_attempts), 1)

    def test_optional_interface_probe_receives_only_the_remaining_budget(self):
        def ping(*_args, **_kwargs):
            self.now = 59
            return PingMetrics()
        self.mocks["measure_ping"].side_effect = ping
        run_iperf3(timeout_seconds=60, **self.options)
        self.mocks["_detect_interface"].assert_called_once_with(timeout_seconds=1)

    def test_expired_optional_probe_does_not_return_an_over_budget_result(self):
        def interface(**_kwargs):
            self.now = 61
            return "fixture"
        self.mocks["_detect_interface"].side_effect = interface
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual(len(captured.exception.target_attempts), 1)


class IperfDiagnosticTests(unittest.TestCase):
    def test_json_refusal_and_busy_are_concise_and_retryable(self):
        for message in ("unable to connect to server: Connection refused", "the server is busy running a test"):
            completed = subprocess.CompletedProcess([], 1, json.dumps({"system_info": "private-machine", "error": message}), "")
            with patch("collector.iperf3_runner.subprocess.run", return_value=completed):
                with self.assertRaises(Iperf3TargetUnavailable) as captured:
                    _run_once_metrics("fixture", "target.example", 5201, 10, 5, False)
            self.assertIn("target.example:5201", str(captured.exception))
            self.assertIn(message, str(captured.exception))
            self.assertNotIn("private-machine", str(captured.exception))

    def test_other_errors_are_not_reclassified_as_refusals(self):
        completed = subprocess.CompletedProcess([], 1, "", "operation timed out")
        with patch("collector.iperf3_runner.subprocess.run", return_value=completed):
            with self.assertRaises(RuntimeError) as captured:
                _run_once_metrics("fixture", "target.example", 5201, 10, 5, False)
        self.assertNotIsInstance(captured.exception, Iperf3TargetUnavailable)
