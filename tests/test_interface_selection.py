# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Preserve interface precedence and bounded best-effort command behavior."""
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from collector.speedtest_runner import _detect_interface, _preferred_interface


class InterfaceSelectionTests(unittest.TestCase):
    def test_first_wired_link_takes_precedence_over_wireless(self):
        output = "wlan0 LOWER_UP\neth1 LOWER_UP\nenp2s0 LOWER_UP\n"
        self.assertEqual(_preferred_interface(output), "eth1")

    def test_first_wireless_is_fallback_without_wired_link(self):
        self.assertEqual(_preferred_interface("wlp1 LOWER_UP\nwlan2 LOWER_UP"), "wlp1")

    def test_virtual_down_link_local_and_malformed_lines_are_ignored(self):
        output = "\nmalformed\nlo LOWER_UP\nveth1 LOWER_UP\nbr-docker LOWER_UP\neth0 DOWN\neth1 LOWER_UP 169.254.1.2\ntun0 LOWER_UP"
        self.assertIsNone(_preferred_interface(output))

    def test_detection_passes_the_remaining_timeout_to_the_command(self):
        with patch("subprocess.run", return_value=SimpleNamespace(stdout="eth0 LOWER_UP")) as execute:
            result = _detect_interface(timeout_seconds=1.25)
        self.assertEqual(result, "eth0")
        self.assertEqual(execute.call_args.args[0], ["ip", "-br", "addr"])
        self.assertAlmostEqual(execute.call_args.kwargs["timeout"], 1.25)

    def test_missing_tool_or_timeout_is_unknown_not_zero_or_an_exception(self):
        for error in (FileNotFoundError(), subprocess.TimeoutExpired("ip", 1)):
            with patch("subprocess.run", side_effect=error):
                self.assertIsNone(_detect_interface(timeout_seconds=1))
