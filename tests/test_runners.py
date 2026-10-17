# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

import json
import subprocess
import unittest
from unittest.mock import patch

from collector.iperf3_runner import Iperf3Timeout, _run_once, run_iperf3
from collector.network_metrics import PingMetrics, measure_ping
from collector.ookla_runner import run_ookla


class RunnerTests(unittest.TestCase):
    def test_ookla_json_is_converted_from_bytes_per_second_to_mbps(self):
        payload = {
            "type": "result",
            "isp": "Example ISP",
            "ping": {"latency": 4.2, "jitter": 0.4, "low": 3.8, "high": 5.1},
            "download": {"bandwidth": 100_000_000},
            "upload": {"bandwidth": 50_000_000},
            "server": {"id": 29564, "name": "Example", "location": "São Paulo"},
            "client": {"country": "Brazil"},
            "interface": {"name": "eth0"},
            "packetLoss": 0,
        }
        completed = subprocess.CompletedProcess(
            args=["speedtest"], returncode=0, stdout=json.dumps(payload), stderr=""
        )
        with patch("collector.ookla_runner.subprocess.run", return_value=completed):
            result = run_ookla(server_ids=[29564])

        self.assertEqual(result.download_mbps, 800)
        self.assertEqual(result.upload_mbps, 400)
        self.assertEqual(result.server_id, 29564)
        self.assertEqual(result.interface, "eth0")
        self.assertEqual(result.latency_min_ms, 3.8)
        self.assertEqual(result.latency_max_ms, 5.1)
        self.assertEqual(result.packet_loss_pct, 0)

    def test_iperf3_extracts_sent_and_received_directions(self):
        payload = {
            "end": {
                "sum_sent": {"bits_per_second": 400_000_000, "retransmits": 3},
                "sum_received": {"bits_per_second": 800_000_000},
            }
        }
        completed = subprocess.CompletedProcess(
            args=["iperf3"], returncode=0, stdout=json.dumps(payload), stderr=""
        )
        with patch("collector.iperf3_runner.subprocess.run", return_value=completed):
            upload = _run_once("iperf3", "example", 5201, 10, 5, reverse=False)
            download = _run_once("iperf3", "example", 5201, 10, 5, reverse=True)

        self.assertEqual(upload, 400)
        self.assertEqual(download, 800)

    def test_ping_metrics_calculate_latency_jitter_and_loss(self):
        output = """PING example (192.0.2.1): 56 data bytes
64 bytes from 192.0.2.1: time=4.0 ms
64 bytes from 192.0.2.1: time=5.0 ms
64 bytes from 192.0.2.1: time=6.0 ms
64 bytes from 192.0.2.1: time=5.0 ms
64 bytes from 192.0.2.1: time=8.0 ms
--- example ping statistics ---
5 packets transmitted, 5 received, 0% packet loss
rtt min/avg/max/mdev = 4.000/5.600/8.000/1.356 ms
"""
        completed = subprocess.CompletedProcess(
            args=["ping"], returncode=0, stdout=output, stderr=""
        )
        with patch("collector.network_metrics.subprocess.run", return_value=completed):
            result = measure_ping("example")

        self.assertEqual(result.ping_ms, 5)
        self.assertEqual(result.latency_min_ms, 4)
        self.assertEqual(result.latency_max_ms, 8)
        self.assertEqual(result.packet_loss_pct, 0)
        self.assertEqual(result.jitter_ms, 1.5)

    def test_iperf3_adds_common_ping_metrics_and_tcp_retransmits(self):
        payload = {
            "end": {
                "sum_sent": {"bits_per_second": 400_000_000, "retransmits": 3},
                "sum_received": {"bits_per_second": 800_000_000},
            }
        }
        completed = subprocess.CompletedProcess(
            args=["iperf3"], returncode=0, stdout=json.dumps(payload), stderr=""
        )
        with patch("collector.iperf3_runner.subprocess.run", return_value=completed), patch(
            "collector.iperf3_runner.measure_ping",
            return_value=PingMetrics(5, 1, 4, 8, 0),
        ), patch(
            "collector.iperf3_runner.resolve_network_identity",
            return_value={"isp": "Vivo", "country": "Brazil", "city": "Curitiba"},
        ):
            result = run_iperf3(server="example")

        self.assertEqual(result.ping_ms, 5)
        self.assertEqual(result.jitter_ms, 1)
        self.assertEqual(result.packet_loss_pct, 0)
        self.assertEqual(result.tcp_retransmits, 6)
        self.assertEqual(result.isp, "Vivo")
        self.assertEqual(result.country, "Brazil")
        self.assertEqual(result.city, "Curitiba")

    def test_iperf3_timeout_uses_total_budget(self):
        with patch(
            "collector.iperf3_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired("iperf3", 60),
        ) as run:
            with self.assertRaises(Iperf3Timeout):
                run_iperf3(server="example", timeout_seconds=60)

        self.assertAlmostEqual(run.call_args.kwargs["timeout"], 60, delta=0.1)
        self.assertTrue(run.call_args.kwargs["start_new_session"])


if __name__ == "__main__":
    unittest.main()
