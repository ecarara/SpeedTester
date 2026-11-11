# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from speedtester_protocol.runner import IperfRunner
from speedtester_protocol.targets import (
    TestTargetEntry,
    choose_target,
    target_identifier,
)


def entry(name, host, priority=100, port=5201):
    return TestTargetEntry(
        name=name,
        target_id=target_identifier(host, port, "external-controlled", "none"),
        target_scope="external-controlled",
        authentication="none",
        host=host,
        port=port,
        country_code="BR",
        region="Sao Paulo",
        city="Sao Paulo",
        priority=priority,
    )


class TargetChoiceTests(unittest.TestCase):
    def test_nearest_probe_wins_even_with_higher_priority_number(self):
        near = entry("near", "138.199.4.1", priority=100)
        far = entry("far", "203.0.113.1", priority=1)
        with patch(
            "speedtester_protocol.targets.target_rtt",
            side_effect=lambda host, port: 0.005 if host == "138.199.4.1" else 0.21,
        ):
            self.assertEqual(choose_target([far, near]).name, "near")

    def test_unreachable_targets_fall_back_to_priority_then_name(self):
        with patch("speedtester_protocol.targets.target_rtt", return_value=None):
            chosen = choose_target(
                [
                    entry("b", "203.0.113.2", priority=20),
                    entry("a", "203.0.113.1", priority=10),
                ]
            )
        self.assertEqual(chosen.name, "a")

    def test_entry_target_id_must_match_host_port_and_authentication(self):
        with self.assertRaises(ValidationError):
            TestTargetEntry(
                name="tampered",
                target_id="central-" + "0" * 64,
                target_scope="external-controlled",
                authentication="none",
                host="138.199.4.1",
                port=5201,
            )


class PublicTargetRetryTests(unittest.TestCase):
    def test_public_runner_retries_the_second_direction_once(self):
        host = "138.199.4.1"
        target_id = target_identifier(host, 5201, "external-controlled", "none")
        runner = IperfRunner(
            host, 5201, target_id=target_id, target_scope="external-controlled"
        )
        grant = SimpleNamespace(
            runner="iperf3",
            target_id=target_id,
            target_scope="external-controlled",
            max_bytes=8192,
            max_duration_ms=30000,
        )
        sent = json.dumps(
            {"end": {"sum_sent": {"bytes": 4096, "bits_per_second": 1_000_000}}}
        )
        received = json.dumps(
            {"end": {"sum_received": {"bytes": 4096, "bits_per_second": 1_000_000}}}
        )
        calls = []

        def capture(command, deadline, max_duration_ms, environment=None):
            calls.append(command)
            if len(calls) == 1:
                return sent.encode()
            if len(calls) == 2:
                raise RuntimeError("iperf_failed")
            return received.encode()

        with (
            patch.object(IperfRunner, "_capture", side_effect=capture),
            patch.object(IperfRunner, "_pause", return_value=None),
        ):
            result = runner(grant)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.upload_mbps, 1.0)
        self.assertEqual(result.download_mbps, 1.0)
