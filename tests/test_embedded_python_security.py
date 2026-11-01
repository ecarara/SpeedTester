# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Release builds must not embed a vulnerable Python interpreter."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_embedded_python as security


class EmbeddedPythonSecurityTests(unittest.TestCase):
    def test_rejects_vulnerable_wrong_series_or_non_cpython(self):
        for version, implementation in (("3.14.9", "CPython"), ("3.14.0", "CPython"),
                                        ("3.15.2", "CPython"), ("3.14.10", "PyPy"),
                                        ("3.14.10rc1", "CPython")):
            with self.subTest(version=version, implementation=implementation):
                with self.assertRaises(ValueError):
                    security.check(version, implementation)
        for version in ("3.14.10", "3.14.11", "3.14.100"):
            security.check(version, "CPython")

    def test_checks_actual_frozen_executable_and_rejects_vulnerable_runtime(self):
        with patch.object(sys, "argv", ["check_embedded_python.py", "/bundle/api"]), \
                patch.object(security.subprocess, "run") as run:
            run.return_value = SimpleNamespace(stdout=json.dumps(
                {"frozen": True, "python": "3.14.9", "implementation": "CPython"}))
            with self.assertRaises(ValueError):
                security.main()
            run.assert_called_once_with(["/bundle/api", "--runtime-info"], check=True,
                                        capture_output=True, text=True, timeout=30)
            run.return_value.stdout = json.dumps(
                {"frozen": True, "python": "3.14.10", "implementation": "CPython"})
            security.main()
            run.return_value.stdout = json.dumps(
                {"frozen": False, "python": "3.14.10", "implementation": "CPython"})
            with self.assertRaises(ValueError):
                security.main()
