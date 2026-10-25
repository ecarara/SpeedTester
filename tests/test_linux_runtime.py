# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Runtime isolation and staging contracts; no compilers or measurements."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_linux_runtime as builder
from shared import frozen_runtime


class NativeEntryTests(unittest.TestCase):
    def test_runtime_info_does_not_import_api_or_collector_or_run_commands(self):
        for name in ("native_api_entry", "native_client_entry", "desktop_launcher"):
            entry = importlib.import_module(name)
            with self.subTest(entry=name), io.StringIO() as output, \
                    contextlib.redirect_stdout(output), \
                    patch.dict(sys.modules, {"api.server": None, "collector.collector": None,
                                             "uvicorn": None}), \
                    patch("subprocess.run", side_effect=AssertionError("no commands")):
                self.assertEqual(entry.main(["--runtime-info"]), 0)
                value = json.loads(output.getvalue())
                self.assertEqual(value["python"], ".".join(map(str, sys.version_info[:3])))
                self.assertEqual(value["implementation"], "CPython")

    def test_api_runs_loaded_app_on_configured_loopback_port_without_worker_spawn(self):
        entry = importlib.import_module("native_api_entry")
        app = object()
        uvicorn = SimpleNamespace(run=Mock())
        server = SimpleNamespace(app=app, settings=SimpleNamespace(api_port=8042))
        with patch.dict(sys.modules, {"uvicorn": uvicorn, "api.server": server}), \
                patch.object(entry, "prepare_system_children") as prepare:
            self.assertEqual(entry.main([]), 0)
        prepare.assert_called_once()
        uvicorn.run.assert_called_once_with(app, host="127.0.0.1", port=8042,
                                            workers=1, loop="asyncio", http="h11")

    def test_linux_system_tools_do_not_inherit_bundle_loader_paths(self):
        for original in (None, "/system/custom-libs"):
            environment = {"LD_LIBRARY_PATH": "/bundle/_internal", "PATH": "/usr/bin:/bin"}
            if original:
                environment["LD_LIBRARY_PATH_ORIG"] = original
            with self.subTest(original=original), patch.dict(os.environ, environment, clear=True), \
                    patch.object(sys, "frozen", True, create=True), patch.object(sys, "platform", "linux"):
                frozen_runtime.prepare_system_children()
                self.assertEqual(os.environ.get("LD_LIBRARY_PATH"), original)
                self.assertNotIn("LD_LIBRARY_PATH_ORIG", os.environ)
                self.assertEqual(os.environ["PATH"], "/usr/bin:/bin")


class LinuxRuntimeTests(unittest.TestCase):
    def runtime(self, root):
        output = root / "runtime"
        output.mkdir()
        document = {"format": "speedtester-linux-runtime-v1", "python": "3.14.9",
                    "app_version": "1.2.3", "architecture": builder.platform.machine(),
                    "libc": {"name": "glibc", "version": "2.35"}}
        (output / "runtime-components.json").write_text(json.dumps(document))
        for name in ("LICENSE", "PYTHON-LICENSE.txt", "THIRD-PARTY-LICENSES"):
            (output / name).touch()
        return output

    def test_verification_checks_each_frozen_interpreter_without_build_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.runtime(Path(temporary))
            info = {"python": "3.14.9", "implementation": "CPython", "frozen": True,
                    "app_version": "1.2.3"}
            with patch.object(builder.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(info))) as run, \
                    patch.dict(os.environ, {"PYTHONPATH": "/host/venv", "PYTHONHOME": "/host/python", "APP_VERSION": "wrong"}):
                builder.verify_runtime(output, "1.2.3")
            self.assertEqual(run.call_count, 3)
            for call in run.call_args_list:
                self.assertEqual(call.args[0][-1], "--runtime-info")
                for key in ("PYTHONPATH", "PYTHONHOME", "APP_VERSION"):
                    self.assertNotIn(key, call.kwargs["env"])

    @unittest.skipIf(os.name == "nt", "POSIX symlink contract")
    def test_host_interpreter_symlink_is_rejected_before_running_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self.runtime(root)
            host = root / "hostedtoolcache/python3.14"
            host.parent.mkdir()
            host.touch()
            (output / "python3.14").symlink_to(host)
            with patch.object(builder.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "symlink escapes"):
                    builder.verify_runtime(output, "1.2.3")
            run.assert_not_called()

    def test_wrong_release_or_nonfrozen_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.runtime(Path(temporary))
            with self.assertRaisesRegex(ValueError, "does not match"):
                builder.verify_runtime(output, "9.9.9")
            with patch.object(builder.subprocess, "run", return_value=SimpleNamespace(stdout='{"python":"3.14.9","frozen":false}')):
                with self.assertRaisesRegex(ValueError, "incorrect frozen"):
                    builder.verify_runtime(output, "1.2.3")

    def test_build_stamps_only_staged_source_and_includes_entire_dashboard(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "app/shared").mkdir(parents=True)
            (source / "app/dashboard").mkdir()
            (source / "app/dashboard/world-map.svg").write_text("fixture map")
            original = source / "app/shared/_build_version.py"
            original.write_text("VERSION = 'unchanged'\n")
            commands = []
            def run(command, **options):
                commands.append(command)
                if command[1].endswith("stamp_version.py"):
                    (Path(command[2]) / "shared/_build_version.py").write_text("VERSION = '1.2.3'\n")
                elif "PyInstaller" in command:
                    staged = Path(command[-1]).parent
                    self.assertNotEqual(staged, source / "app")
                    self.assertIn("1.2.3", (staged / "shared/_build_version.py").read_text())
                    self.assertEqual((staged / "dashboard/world-map.svg").read_text(), "fixture map")
                return SimpleNamespace(returncode=0)
            with patch.object(builder, "ROOT", source), patch.object(builder, "check_environment"), \
                    patch.object(builder, "copy_notices", return_value=[]), \
                    patch.object(builder, "verify_runtime"), \
                    patch.object(builder.platform, "libc_ver", return_value=("glibc", "2.35")), \
                    patch.object(builder.subprocess, "run", side_effect=run):
                builder.build(root / "output", "1.2.3")
            self.assertEqual(original.read_text(), "VERSION = 'unchanged'\n")
            freezes = [command for command in commands if "PyInstaller" in command]
            self.assertEqual(len(freezes), 3)
            self.assertTrue(all("--onedir" in command for command in freezes))
            api = next(command for command in freezes if command[-1].endswith("native_api_entry.py"))
            self.assertTrue(api[api.index("--add-data") + 1].endswith("/app/dashboard:dashboard"))
            self.assertFalse(any(str(source / "app") in argument for command in freezes for argument in command))


if __name__ == "__main__":
    unittest.main()
