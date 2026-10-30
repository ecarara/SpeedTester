# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Geographic recovery with synthetic runners; never contact public targets."""
import json
import subprocess
from dataclasses import replace
import unittest
from unittest.mock import patch

from collector.iperf3_runner import (
    Iperf3ResourceError, Iperf3TargetUnavailable, Iperf3Timeout, IperfRunMetrics, _alternate_tmpdir,
    _run_once_metrics, run_iperf3,
)
from collector.network_metrics import PingMetrics
from collector.network_link import NetworkLink
from collector.target_selection import TARGETS, Target, TargetSelectionError, rank_targets


class TargetRankingTests(unittest.TestCase):
    def test_sao_paulo_fortisase_has_only_the_advertised_port_range(self):
        target = next(t for t in TARGETS if t.host == "148.230.60.200")
        self.assertEqual((target.port, *target.alternate_ports),
                         (30001, 30002, 30003, 30004, 30005, 30006, 30007, 30008, 30009))

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
            "detect_link": dict(return_value=NetworkLink("fixture", "ethernet", "fixture")),
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

    def test_busy_first_host_and_refused_primary_port_use_advertised_alternate(self):
        self.mocks["rank_targets"].return_value = (
            self.targets[0], replace(self.targets[1], port=30001, alternate_ports=(30002, 30003)),
            self.targets[2],
        )
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [Iperf3TargetUnavailable("busy"), Iperf3TargetUnavailable("refused"),
                               self.metrics, self.metrics]
        result = run_iperf3(**self.options)
        self.assertEqual([(c.args[1], c.args[2], c.kwargs["reverse"]) for c in execute.call_args_list], [
            (self.targets[0].host, 5201, False), (self.targets[1].host, 30001, False),
            (self.targets[1].host, 30002, False), (self.targets[1].host, 30002, True),
        ])
        self.assertEqual(result.server_name, "iperf3:target-2.example:30002")
        self.assertEqual([a["server_name"] for a in result.target_attempts], [
            "iperf3:target-1.example:5201", "iperf3:target-2.example:30001", "iperf3:target-2.example:30002"])
        self.assertEqual([a["outcome"] for a in result.target_attempts], ["error", "error", "selected"])

    def test_failed_download_on_one_port_restarts_both_directions_on_next(self):
        self.mocks["rank_targets"].return_value = (replace(self.targets[0], port=30001, alternate_ports=(30002,)),)
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [IperfRunMetrics(123, 99, 100), Iperf3TargetUnavailable("busy"),
                               IperfRunMetrics(500, 2, 200), IperfRunMetrics(900, 3, 300)]
        result = run_iperf3(**self.options)
        self.assertEqual([(c.args[2], c.kwargs["reverse"]) for c in execute.call_args_list],
                         [(30001, False), (30001, True), (30002, False), (30002, True)])
        self.assertEqual((result.upload_mbps, result.download_mbps, result.transfer_bytes), (500, 900, 500))
        self.assertEqual([a["outcome"] for a in result.target_attempts], ["download_error", "selected"])

    def test_after_all_advertised_ports_fail_next_geographic_host_is_used(self):
        self.mocks["rank_targets"].return_value = (
            replace(self.targets[0], port=30001, alternate_ports=tuple(range(30002, 30010))),
            self.targets[1],
        )
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [Iperf3TargetUnavailable("busy") for _ in range(9)] + [self.metrics, self.metrics]
        result = run_iperf3(**self.options)
        self.assertEqual([c.args[2] for c in execute.call_args_list[:9]],
                         [30001, 30002, 30003, 30004, 30005, 30006, 30007, 30008, 30009])
        self.assertEqual(result.server_name, "iperf3:target-2.example:5201")
        self.assertEqual(len(result.target_attempts), 10)

    def test_manual_target_never_uses_alternate_ports(self):
        self.mocks["rank_targets"].return_value = (replace(self.targets[0], mode="manual", alternate_ports=(30002,)),)
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = Iperf3TargetUnavailable("busy")
        with self.assertRaises(Iperf3TargetUnavailable):
            run_iperf3(server="target-1.example", **self.options)
        self.assertEqual(execute.call_count, 1)

    def test_deadline_stops_alternate_ports_without_an_extra_process(self):
        self.mocks["rank_targets"].return_value = (replace(self.targets[0], port=30001, alternate_ports=(30002,)),)
        def refuse(*_args, **_kwargs):
            self.now = 60
            raise Iperf3TargetUnavailable("busy")
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = refuse
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(len(captured.exception.target_attempts), 1)

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

    def test_control_disconnect_fails_over_and_resource_failure_does_not(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [Iperf3TargetUnavailable("control channel disconnected"),
                               self.metrics, self.metrics]
        self.assertEqual(run_iperf3(**self.options).server_name, "iperf3:target-2.example:5201")
        self.assertEqual(execute.call_count, 3)
        execute.reset_mock()
        execute.side_effect = Iperf3ResourceError("failed to read /dev/urandom")
        with self.assertRaises(Iperf3ResourceError):
            run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 1)

    def test_temporary_directory_recovery_restarts_pair_on_same_target(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = [IperfRunMetrics(123, 99, 100),
                               Iperf3ResourceError("failed to read /dev/urandom: Bad address"),
                               IperfRunMetrics(500, 2, 200), IperfRunMetrics(900, 3, 300)]
        with patch("collector.iperf3_runner._alternate_tmpdir", return_value="/dev/shm"):
            result = run_iperf3(**self.options)
        self.assertEqual([call.args[1] for call in execute.call_args_list],
                         ["target-1.example"] * 4)
        self.assertEqual([call.kwargs["reverse"] for call in execute.call_args_list],
                         [False, True, False, True])
        self.assertNotIn("temporary_directory", execute.call_args_list[0].kwargs)
        self.assertEqual(execute.call_args_list[2].kwargs["temporary_directory"], "/dev/shm")
        self.assertEqual((result.upload_mbps, result.download_mbps, result.transfer_bytes), (500, 900, 500))
        self.assertEqual([a["outcome"] for a in result.target_attempts], ["download_error", "selected"])
        self.assertTrue(result.target_attempts[-1]["temporary_directory_recovery"])

    def test_recovery_is_attempted_once_and_stays_within_original_timeout(self):
        execute = self.mocks["_run_once_metrics"]
        execute.side_effect = Iperf3ResourceError("failed to read /dev/urandom: Bad address")
        with patch("collector.iperf3_runner._alternate_tmpdir", return_value="/dev/shm"):
            with self.assertRaises(Iperf3ResourceError) as captured:
                run_iperf3(**self.options)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(len(captured.exception.target_attempts), 2)
        execute.reset_mock()
        def fail_after_deadline(*_args, **_kwargs):
            self.now = 60
            raise Iperf3ResourceError("failed to read /dev/urandom: Bad address")
        execute.side_effect = fail_after_deadline
        with patch("collector.iperf3_runner._alternate_tmpdir", return_value="/dev/shm"):
            with self.assertRaises(Iperf3Timeout):
                run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual(execute.call_count, 1)

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
        self.assertEqual(self.mocks["detect_link"].call_args.kwargs["timeout_seconds"], 1)

    def test_expired_optional_probe_does_not_return_an_over_budget_result(self):
        def interface(**_kwargs):
            self.now = 61
            return NetworkLink("fixture", "ethernet", "fixture")
        self.mocks["detect_link"].side_effect = interface
        with self.assertRaises(Iperf3Timeout) as captured:
            run_iperf3(timeout_seconds=60, **self.options)
        self.assertEqual(len(captured.exception.target_attempts), 1)


class IperfDiagnosticTests(unittest.TestCase):
    def test_alternate_directory_must_be_distinct_available_and_linux(self):
        with patch('collector.iperf3_runner.platform.system', return_value='Linux'), \
             patch('collector.iperf3_runner.os.path.isdir', return_value=True), \
             patch('collector.iperf3_runner.os.access', return_value=True), \
             patch.dict('os.environ', {'TMPDIR': '/tmp'}, clear=True):
            self.assertEqual(_alternate_tmpdir(), '/dev/shm')
            with patch.dict('os.environ', {'TMPDIR': '/dev/shm'}, clear=True):
                self.assertIsNone(_alternate_tmpdir())
            with patch('collector.iperf3_runner.os.access', return_value=False):
                self.assertIsNone(_alternate_tmpdir())
        with patch('collector.iperf3_runner.platform.system', return_value='Windows'):
            self.assertIsNone(_alternate_tmpdir())

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

    def test_disconnected_control_channel_can_fail_over_but_resource_failure_cannot(self):
        from collector.collector import Collector
        cases = [
            ('unable to receive control message: Transport endpoint is not connected', Iperf3TargetUnavailable),
            ('iperf3: error - failed to read /dev/urandom: Bad address', Iperf3ResourceError),
        ]
        for message, error_type in cases:
            completed = subprocess.CompletedProcess([], 1, '', message)
            with self.subTest(message=message), patch('collector.iperf3_runner.subprocess.run', return_value=completed):
                with self.assertRaises(error_type) as captured:
                    _run_once_metrics('fixture', 'target.example', 5201, 10, 5, False)
                if error_type is Iperf3ResourceError:
                    self.assertEqual(Collector._classify_failure(None, captured.exception), 'iperf_resource')
                    self.assertNotIsInstance(captured.exception, Iperf3TargetUnavailable)
