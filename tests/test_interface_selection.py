# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Local-link evidence uses native routes, never adapter-name preferences."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from collector.network_link import (_Probe, _linux, _mac, _windows, _windows_type,
                                    detect_link, literal_ip)


class InterfaceSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def device(self, name, *, wifi=False, physical=True, hardware_type="1", uevent=""):
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        (directory / "type").write_text(hardware_type)
        (directory / "uevent").write_text(uevent)
        if wifi:
            (directory / "wireless").mkdir()
        if physical:
            (directory / "device").mkdir()

    def linux(self, *, local=None, remote=None, hint=None, v4=None, v6=None, addresses=None, kind=None):
        def output(command):
            if "address" in command:
                return json.dumps(addresses or [])
            if "-d" in command:
                return json.dumps([{"linkinfo": {"info_kind": kind}}])
            return json.dumps(v6 or [] if "-6" in command else v4 or [])
        return _linux(SimpleNamespace(run=Mock(side_effect=output)), local, remote, hint, self.root)

    def test_active_wired_adapter_does_not_override_wifi_route(self):
        self.device("enp1")
        self.device("wlp1", wifi=True)
        link = self.linux(v4=[{"dev": "wlp1"}])
        self.assertEqual((link.interface, link.connection_type, link.scope), ("wlp1", "wifi", "default_route"))

    def test_native_source_address_overrides_default(self):
        self.device("custom", wifi=True)
        link = self.linux(local="192.0.2.10", v4=[{"dev": "ethernet"}],
            addresses=[{"ifname": "custom", "addr_info": [{"local": "192.0.2.10"}]}])
        self.assertEqual((link.interface, link.connection_type, link.scope), ("custom", "wifi", "runner_address"))

    def test_physical_metadata_identifies_ethernet_without_name_heuristic(self):
        self.device("my-uplink")
        self.assertEqual(self.linux(hint="my-uplink").connection_type, "ethernet")

    def test_container_eth0_is_virtual_not_cabled(self):
        self.device("eth0", physical=False)
        self.assertEqual(self.linux(hint="eth0", kind="veth").connection_type, "virtual")
        self.assertEqual(self.linux(hint="eth0").connection_type, "unknown")

    def test_other_linux_links(self):
        for name, hardware, uevent, native_kind, expected in [
            ("lo", "772", "", None, "loopback"), ("ppp0", "512", "", None, "point_to_point"),
            ("wwan0", "1", "DEVTYPE=wwan", None, "cellular"),
            ("wg0", "1", "", "wireguard", "tunnel"), ("bond0", "1", "", "bond", "virtual")]:
            with self.subTest(name=name):
                self.device(name, physical=False, hardware_type=hardware, uevent=uevent)
                self.assertEqual(self.linux(hint=name, kind=native_kind).connection_type, expected)

    def test_ambiguous_default_routes_are_unknown(self):
        self.device("wifi", wifi=True)
        self.device("wired")
        for v4, v6 in [([{"dev": "wifi"}], [{"dev": "wired"}]),
                       ([{"dev": "wifi", "metric": 10}, {"dev": "wired", "metric": 10}], [])]:
            with self.subTest(v4=v4, v6=v6):
                self.assertIsNone(self.linux(v4=v4, v6=v6).interface)
        self.assertEqual(self.linux(v4=[{"dev": "wifi", "metric": 5},
                                      {"dev": "wired", "metric": 10}]).connection_type, "wifi")

    def test_unmapped_native_address_does_not_fall_back_to_another_link(self):
        self.device("wired")
        self.assertIsNone(self.linux(local="192.0.2.10", v4=[{"dev": "wired"}]).interface)

    def test_destination_route_uses_literal_ip(self):
        self.device("wifi", wifi=True)
        link = self.linux(remote="2001:db8::1", v4=[{"dev": "wifi"}])
        self.assertEqual((link.connection_type, link.scope), ("wifi", "destination_route"))

    def test_macos_en0_can_be_wifi(self):
        probe = SimpleNamespace(run=Mock(side_effect=["interface: en0", "interface: en0",
            "Hardware Port: Wi-Fi\nDevice: en0\nEthernet Address: private\n"]))
        link = _mac(probe, None, None, None)
        self.assertEqual((link.interface, link.connection_type), ("en0", "wifi"))
        self.assertNotIn("private", json.dumps(link.evidence()))

    def test_macos_native_ipv6_source_maps_to_ethernet(self):
        probe = SimpleNamespace(run=Mock(side_effect=["en4: flags\n\tinet6 2001:db8::2 prefixlen 64\n",
            "Hardware Port: USB 10/100/1000 LAN\nDevice: en4\n"]))
        link = _mac(probe, "2001:db8::2", None, None)
        self.assertEqual((link.connection_type, link.scope), ("ethernet", "runner_address"))

    def test_macos_other_links_and_ambiguous_defaults(self):
        for name, port, expected in [("en5", "iPhone USB", "usb"), ("en6", "Bluetooth PAN", "bluetooth"),
                                     ("bridge0", "Thunderbolt Bridge", "virtual"),
                                     ("en7", "Unrecognized", "unknown"),
                                     ("utun2", "", "tunnel"), ("lo0", "", "loopback")]:
            probe = SimpleNamespace(run=Mock(return_value=f"Hardware Port: {port}\nDevice: {name}\n"))
            self.assertEqual(_mac(probe, None, None, name).connection_type, expected)
        probe = SimpleNamespace(run=Mock(side_effect=["interface: en0", "interface: en1"]))
        self.assertIsNone(_mac(probe, None, None, None).interface)

    def test_windows_uses_physical_medium_not_ethernet_style_iftype_alone(self):
        for medium, expected in [(1, "wifi"), (9, "wifi"), (14, "ethernet"),
                                 (8, "cellular"), (10, "bluetooth"), (0, "unknown")]:
            self.assertEqual(_windows_type({"hardware": True, "physical_medium": medium, "interface_type": 6}), expected)
        for row, expected in [({"virtual": True, "physical_medium": 14}, "virtual"),
                              ({"hardware": False}, "virtual"), ({"interface_type": 131}, "tunnel"),
                              ({"interface_type": 24}, "loopback")]:
            self.assertEqual(_windows_type(row), expected)

    def test_windows_dynamic_adapter_name_stays_in_stdin_not_script(self):
        name = "Wi-Fi '; Remove-Item anything; '"
        probe = SimpleNamespace(run=Mock(return_value=json.dumps({"name": name, "hardware": True,
            "physical_medium": 9, "scope": "runner_interface"})))
        link = _windows(probe, None, None, name)
        self.assertEqual(link.connection_type, "wifi")
        self.assertNotIn(name, probe.run.call_args.args[0][-1])
        self.assertEqual(json.loads(probe.run.call_args.kwargs["input"])["hint"], name)

    def test_commands_share_one_deadline(self):
        completed = SimpleNamespace(stdout="ok", returncode=0)
        with patch("collector.network_link.time.monotonic", side_effect=[0, 0, .7, 1.1]), \
                patch("collector.network_link.subprocess.run", return_value=completed) as execute:
            probe = _Probe(1)
            self.assertEqual(probe.run(["one"]), "ok")
            self.assertEqual(probe.run(["two"]), "ok")
            self.assertEqual(probe.run(["three"]), "")
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(execute.call_args_list[0].kwargs["timeout"], 1)
        self.assertAlmostEqual(execute.call_args_list[1].kwargs["timeout"], .3)

    def test_missing_tool_timeout_or_malformed_metadata_is_nonfatal(self):
        for error in (FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired("ip", 1)):
            with patch("collector.network_link.platform.system", return_value="Linux"), \
                    patch("collector.network_link.subprocess.run", side_effect=error):
                self.assertEqual(detect_link().connection_type, "unknown")
        for output in ("not JSON", "[]", '{"physical_medium":14,"hardware":true}'):
            self.assertEqual(_windows(SimpleNamespace(run=lambda *args, **kwargs: output), None, None, None).connection_type, "unknown")
        with patch("collector.network_link.platform.system", return_value="Unsupported"):
            self.assertEqual(detect_link().connection_type, "unknown")

    def test_invalid_names_and_nonliteral_addresses_do_not_run_shell_or_dns(self):
        with patch("collector.network_link.subprocess.run") as execute:
            result = detect_link(interface_hint="../../private", local_ip="host.example", timeout_seconds=0)
        self.assertEqual(result.connection_type, "unknown")
        execute.assert_not_called()
        self.assertEqual(literal_ip("2001:db8::1%en0"), "2001:db8::1")
        self.assertIsNone(literal_ip("0.0.0.0"))
