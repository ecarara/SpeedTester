# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Coverage for repository hygiene scripts touched by the Sonar cleanup."""
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.publication = _load("check_publication")

    def test_private_network_and_address_detection(self):
        self.assertTrue(self.publication._has_private_ipv4("10.0.0.1"))
        self.assertTrue(self.publication._has_private_ipv4("172.16.0.1"))
        self.assertTrue(self.publication._has_private_ipv4("192.168.0.1"))
        self.assertFalse(self.publication._has_private_ipv4("8.8.8.8"))
        self.assertFalse(self.publication._has_private_ipv4("not-an-ip"))

    def test_scan_and_main_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ok.py").write_text("print('ok')")
            (root / "secret.txt").write_text("ghp_" + "a" * 24)
            (root / "private.txt").write_text("10.0.0.1")
            (root / ".env").write_text("X=1")
            (root / "data").mkdir()
            (root / "data" / "stored.txt").write_text("value")
            code = self.publication
            with patch.object(code, "ROOT", root):
                self.assertEqual(code._artifact_reason(root / ".env"), "local artifact")
                self.assertEqual(code._artifact_reason(root / "db.sqlite"), "local artifact")
                self.assertEqual(code._artifact_reason(root / "data" / "stored.txt"), "local artifact")
                self.assertIsNone(code._artifact_reason(root / "ok.py"))
                self.assertEqual(code._scan_file(root / "secret.txt", "secret.txt"), "possible secret")
                self.assertEqual(code._scan_file(root / "private.txt", "private.txt"), "private IPv4 literal")
                with patch.object(code, "_listed_paths", return_value=["ok.py"]):
                    with patch("sys.stdout", new_callable=io.StringIO):
                        self.assertEqual(code.main(), 0)
                with patch.object(code, "_listed_paths", return_value=[".env"]):
                    with patch("sys.stdout", new_callable=io.StringIO):
                        self.assertEqual(code.main(), 1)


class CheckLicenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.license = _load("check_license")

    def test_repository_metadata_passes(self):
        with patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.license.main(), 0)

    def test_missing_markers_are_reported(self):
        with patch.object(self.license, "REQUIRED_LICENSE_MARKERS", ("missing",)):
            self.assertTrue(self.license._license_errors())
        with patch.object(self.license, "ROOT", Path("/nonexistent")):
            self.assertEqual(self.license._reuse_errors(), ["REUSE.toml is missing"])


class CompareRunnersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compare = _load("compare_runners")

    def _settings(self):
        return SimpleNamespace(
            sample_duration_seconds=10,
            speedtest_server_ids=None,
            max_bytes=10_000_000,
            bandwidth_contracted_mbps=1000.0,
            isp_lookup_enabled=False,
            isp_lookup_timeout_seconds=5.0,
            ookla_binary="speedtest",
            iperf3_server="iperf3.example.com",
            iperf3_port=5202,
            iperf3_duration_seconds=10,
            iperf3_parallel_streams=5,
            measurement_timeout_seconds=60,
        )

    def test_main_builds_iperf3_target_and_reports_errors(self):
        from collector.speedtest_runner import SpeedTestResult

        result = SpeedTestResult(1, 2, 3, 4, 5, 6, None, None, None, None, None, None,
                                 "eth0", None, None, 1.0)
        with patch.object(self.compare, "load_settings", return_value=self._settings()), \
             patch.object(self.compare, "run_named_runner", return_value=result) as runner, \
             patch.object(sys, "argv", ["compare_runners.py", "--runners", "iperf3"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.compare.main(), 0)
            target = runner.call_args.kwargs["iperf3_target"]
            self.assertEqual((target.server, target.port), ("iperf3.example.com", 5202))
        with patch.object(self.compare, "load_settings", return_value=self._settings()), \
             patch.object(self.compare, "run_named_runner", side_effect=RuntimeError("boom")), \
             patch.object(sys, "argv", ["compare_runners.py", "--runners", "iperf3"]), \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(self.compare.main(), 1)
