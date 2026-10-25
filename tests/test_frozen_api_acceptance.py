# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Acceptance-runner failures must stop children and discard isolated state.

The real frozen API is exercised in native CI. These fixtures exercise process
failure, HTTP rejection and timeout paths without an API or measurement runner.
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import test_frozen_api as acceptance


class FrozenApiAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.executable = Path(temporary.name) / "SpeedTesterAPI"
        self.executable.touch()
        self.process = Mock(spec=("poll", "terminate", "wait", "kill"))
        self.process.poll.return_value = None
        self.process.wait.return_value = 0
        self.enterContext(patch.object(acceptance, "WINDOWS", False))
        self.runtime = self.enterContext(patch.object(acceptance.subprocess, "check_output",
            return_value=json.dumps({"python": "3.14.9", "frozen": True})))
        self.popen = self.enterContext(patch.object(acceptance.subprocess, "Popen", side_effect=self.spawn))
        self.http = self.enterContext(patch.object(acceptance.urllib.request, "urlopen", side_effect=self.response))
        self.stdout = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))

    def spawn(self, *_args, **options):
        options["stdout"].write(b"synthetic API startup diagnostic\n")
        options["stdout"].flush()
        return self.process

    def response(self, url, **_options):
        path = urlsplit(url).path
        content = {"/api/auth/session": b'{"login_required": false}',
                   "/api/chart.png": b"\x89PNG\r\n\x1a\nfixture"}.get(path, b"fixture response")
        response = io.BytesIO(content)
        response.status = 200
        return response

    def assert_cleaned(self, *, killed=False):
        self.process.terminate.assert_called_once_with()
        self.assertEqual(self.process.wait.call_args_list,
                         [call(timeout=15), call(timeout=5)] if killed else [call(timeout=15)])
        if killed:
            self.process.kill.assert_called_once_with()
        else:
            self.process.kill.assert_not_called()
        options = self.popen.call_args.kwargs
        self.assertFalse(options["cwd"].exists(), "isolated DB, cache and log must be removed")
        self.assertTrue(options["stdout"].closed)

    def test_wrong_python_or_unfrozen_runtime_is_refused_before_launch(self):
        for runtime in ({"python": "3.15.1", "frozen": True},
                        {"python": "3.14.9", "frozen": False},
                        {"python": "3.14.9"}, {"python": "3.14.9", "frozen": "true"}):
            with self.subTest(runtime=runtime):
                self.runtime.return_value = json.dumps(runtime)
                with self.assertRaises(AssertionError):
                    acceptance.check(self.executable)
                self.popen.assert_not_called()
                self.http.assert_not_called()
        self.assertEqual(self.stdout.getvalue(), "")

    def test_failed_runtime_diagnostic_does_not_start_api(self):
        self.runtime.side_effect = subprocess.CalledProcessError(1, "runtime-info")
        with self.assertRaises(subprocess.CalledProcessError):
            acceptance.check(self.executable)
        self.popen.assert_not_called()
        self.http.assert_not_called()

    def test_windows_onefile_child_is_stopped_by_exact_process_tree(self):
        process = Mock(pid=12345)
        with patch.object(acceptance, "WINDOWS", True), \
                patch.object(acceptance.subprocess, "run", return_value=Mock(returncode=0)) as terminate:
            acceptance.stop_process(process)
        self.assertEqual(terminate.call_args.args[0],
                         ['taskkill', '/PID', '12345', '/T', '/F'])
        process.terminate.assert_not_called()
        process.wait.assert_called_once_with(timeout=15)

    def test_windows_tree_failure_is_reported_only_if_api_is_still_running(self):
        for exit_status in (None, 1):
            process = Mock(pid=12345)
            process.poll.return_value = exit_status
            with self.subTest(exit_status=exit_status), patch.object(acceptance, "WINDOWS", True), \
                    patch.object(acceptance.subprocess, "run", return_value=Mock(returncode=1, stderr='denied')):
                if exit_status is None:
                    with self.assertRaisesRegex(RuntimeError, 'process tree: denied'):
                        acceptance.stop_process(process)
                    process.wait.assert_not_called()
                else:
                    acceptance.stop_process(process)
                    process.wait.assert_called_once_with(timeout=15)

    def test_startup_crash_reports_log_and_stops_process_without_hanging(self):
        self.http.side_effect = OSError("connection refused")
        self.process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "synthetic API startup diagnostic"):
            acceptance.check(self.executable)
        self.assert_cleaned()
        self.assertNotIn("frozen-api-ok", self.stdout.getvalue())

    def test_startup_deadline_stops_a_live_but_unresponsive_api(self):
        self.http.side_effect = OSError("not ready")
        with patch.object(acceptance.time, "monotonic", side_effect=[0, 61]), \
                patch.object(acceptance.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "startup diagnostic"):
                acceptance.check(self.executable)
        sleep.assert_not_called()
        self.assert_cleaned()

    def test_transient_health_failure_retries_in_isolated_environment_then_cleans_up(self):
        attempts = 0
        def request(url, **options):
            nonlocal attempts
            if urlsplit(url).path == "/health":
                attempts += 1
                if attempts == 1:
                    raise OSError("connection not ready yet")
            return self.response(url, **options)
        self.http.side_effect = request
        with patch.object(acceptance.time, "sleep") as sleep:
            acceptance.check(self.executable)
        self.assertEqual(attempts, 2)
        sleep.assert_called_once_with(0.2)
        options = self.popen.call_args.kwargs
        self.assertEqual(self.popen.call_args.args[0], [str(self.executable.resolve())])
        self.assertEqual(Path(options["env"]["DB_PATH"]).parent, options["cwd"])
        self.assertEqual(Path(options["env"]["MPLCONFIGDIR"]).parent, options["cwd"])
        self.assertEqual(Path(options["env"]["SPEEDTESTER_CONFIG_FILE"]).parent, options["cwd"])
        self.assertEqual(options["env"]["ISP_LOOKUP_ENABLED"], "false")
        self.assert_cleaned()

    def test_missing_asset_is_failure_and_still_terminates_the_api(self):
        def request(url, **options):
            if urlsplit(url).path == "/dashboard/world-map.svg":
                raise OSError("missing frozen dashboard asset")
            return self.response(url, **options)
        self.http.side_effect = request
        with self.assertRaisesRegex(OSError, "missing frozen dashboard asset"):
            acceptance.check(self.executable)
        self.assert_cleaned()
        self.assertNotIn("frozen-api-ok", self.stdout.getvalue())

    def test_bad_http_status_empty_asset_login_and_invalid_chart_all_fail_with_cleanup(self):
        cases = (("/health", 503, b"unhealthy"),
                 ("/api/summary", 500, b"error"),
                 ("/dashboard/charts.js", 200, b""),
                 ("/api/auth/session", 200, b'{"login_required": true}'),
                 ("/api/chart.png", 200, b"not a PNG"))
        for path, status, body in cases:
            with self.subTest(path=path):
                self.process.reset_mock()
                def request(url, **options):
                    if urlsplit(url).path == path:
                        response = io.BytesIO(body)
                        response.status = status
                        return response
                    return self.response(url, **options)
                self.http.side_effect = request
                with self.assertRaises(AssertionError):
                    acceptance.check(self.executable)
                self.assert_cleaned()
                self.assertNotIn("frozen-api-ok", self.stdout.getvalue())

    def test_unresponsive_shutdown_is_killed_and_waited_for(self):
        self.process.wait.side_effect = [subprocess.TimeoutExpired("api", 15), 0]
        self.http.side_effect = OSError("boot failed")
        self.process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "startup diagnostic"):
            acceptance.check(self.executable)
        self.assert_cleaned(killed=True)

    def test_spawn_failure_discards_temporary_directory_and_closes_log(self):
        self.popen.side_effect = OSError("not executable")
        with self.assertRaisesRegex(OSError, "not executable"):
            acceptance.check(self.executable)
        options = self.popen.call_args.kwargs
        self.assertFalse(options["cwd"].exists())
        self.assertTrue(options["stdout"].closed)
        self.process.terminate.assert_not_called()
        self.http.assert_not_called()

    def test_cli_requires_an_explicit_executable_without_starting_processes(self):
        with patch.object(sys, "argv", ["test_frozen_api.py"]), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                runpy.run_path(str(ROOT / "scripts/test_frozen_api.py"), run_name="__main__")
        self.assertEqual(error.exception.code, 2)
        self.popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
