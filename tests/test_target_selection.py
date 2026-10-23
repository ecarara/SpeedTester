# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise the destination used by the shipped collector, not just the SDK."""
import subprocess
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from collector.iperf3_runner import IperfRunMetrics, run_iperf3
from collector.network_metrics import PingMetrics
from collector.target_selection import Target, TargetSelectionError, coordinates, select_target


class GeographicSelectionTests(unittest.TestCase):
    def test_nearest_city_wins_even_across_a_country_border(self):
        targets = (
            Target("far.example", country_code="BR", city="São Paulo", latitude=-23.55, longitude=-46.63, capacity_gbps=100),
            Target("near.example", country_code="PY", city="Ciudad del Este", latitude=-25.51, longitude=-54.61, capacity_gbps=10),
        )
        chosen = select_target(location={"country_code": "BR", "latitude": -25.54, "longitude": -54.59}, targets=targets)
        self.assertEqual(chosen.host, "near.example")
        self.assertLess(chosen.distance_km, 5)

    def test_explicit_server_and_port_always_win(self):
        chosen = select_target("manual.example", 5300, location={"latitude": -23.55, "longitude": -46.63})
        self.assertEqual((chosen.host, chosen.port, chosen.mode), ("manual.example", 5300, "manual"))
        self.assertIsNone(chosen.distance_km)

    def test_empty_server_enables_automatic_selection(self):
        chosen = select_target("  ", location={"latitude": -23.55, "longitude": -46.63})
        self.assertEqual(chosen.city, "São Paulo")
        self.assertEqual(chosen.mode, "automatic")

    def test_missing_location_is_not_replaced_by_random_server(self):
        with self.assertRaises(TargetSelectionError):
            select_target(location={})
        for value in (float("nan"), float("inf"), 91, True):
            self.assertIsNone(coordinates({"latitude": value, "longitude": 0}))
        self.assertEqual(coordinates({"latitude": 0, "longitude": 0}), (0.0, 0.0))

    def test_city_match_normalizes_accents_and_country_fallback_is_explicit(self):
        chosen = select_target(location={"country_code": "br", "city": "SAO PAULO"})
        self.assertEqual(chosen.mode, "automatic-city")
        self.assertEqual(chosen.country_code, "BR")
        self.assertEqual(select_target(location={"country_code": "BR"}).mode, "automatic-country")

    def test_shipped_runner_executes_both_directions_on_selected_destination(self):
        identity = {"latitude": -23.55, "longitude": -46.63, "city": "São Paulo", "country_code": "BR"}
        with patch("collector.iperf3_runner.resolve_network_identity", return_value=identity) as lookup, \
                patch("collector.iperf3_runner._run_once_metrics", return_value=IperfRunMetrics(900, 0, 1024)) as execute, \
                patch("collector.iperf3_runner.measure_ping", return_value=PingMetrics(5, 1, 4, 6, 0)):
            result = run_iperf3(server=None)
        self.assertEqual(lookup.call_count, 1)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args_list[0].args[1:3], execute.call_args_list[1].args[1:3])
        self.assertEqual(result.server_location, "São Paulo, BR")
        self.assertEqual(result.target_selection, "automatic")

    def test_manual_mode_does_not_geolocate_or_replace_an_unreachable_host(self):
        with patch("collector.iperf3_runner.resolve_network_identity") as lookup, \
                patch("collector.iperf3_runner._run_once_metrics", side_effect=RuntimeError("unreachable")) as execute:
            with self.assertRaisesRegex(RuntimeError, "unreachable"):
                run_iperf3(server="manual.example", port=5300)
        lookup.assert_not_called()
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(execute.call_args.args[1:3], ("manual.example", 5300))


@unittest.skipIf(__import__("os").name == "nt", "POSIX installer")
class InstallerSelectionTests(unittest.TestCase):
    def test_package_configuration_allows_empty_host_and_preserves_manual_on_upgrade(self):
        import os
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            environment = dict(os.environ, SPEEDTESTER_CONFIG_DIR=temporary, SPEEDTESTER_NONINTERACTIVE="1",
                               SPEEDTESTER_ENV_TEMPLATE=str(root / "packaging/linux/speedtester.env.example"))
            environment.pop("SPEEDTESTER_ENV_FILE", None)
            command = ["bash", str(root / "packaging/linux/configure-user.sh")]
            first = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
            config = Path(temporary) / "speedtester.env"
            self.assertIn("IPERF3_SERVER=\n", config.read_text())
            self.assertIn("seleção automática", first.stdout)
            config.write_text(config.read_text().replace("IPERF3_SERVER=\n", "IPERF3_SERVER=manual.example\n"))
            subprocess.run(command, env=dict(environment, SPEEDTESTER_CONFIRM_EXISTING="1"), capture_output=True, check=True)
            self.assertIn("IPERF3_SERVER=manual.example\n", config.read_text())
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)
            subprocess.run(command, env=dict(environment, SPEEDTESTER_CONFIRM_EXISTING="1",
                SPEEDTESTER_IPERF3_SERVER="chosen.example", SPEEDTESTER_IPERF3_PORT="5300"), capture_output=True, check=True)
            self.assertIn("IPERF3_SERVER=chosen.example\n", config.read_text())
            self.assertIn("IPERF3_PORT=5300\n", config.read_text())
            subprocess.run(command, env=dict(environment, SPEEDTESTER_CONFIRM_EXISTING="1",
                SPEEDTESTER_IPERF3_SERVER=""), capture_output=True, check=True)
            self.assertIn("IPERF3_SERVER=\n", config.read_text())
