# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Runtime isolation and staging contracts; no compilers or measurements."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
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

    def test_inventory_cannot_claim_another_interpreter_architecture_or_libc(self):
        changes = ({"format": "unknown"}, {"python": "3.15.1"},
                   {"architecture": "different-target"}, {"libc": {"name": "musl", "version": "1.2"}},
                   {"libc": {"name": "glibc", "version": "unknown"}})
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                output = self.runtime(Path(temporary))
                inventory = output / "runtime-components.json"
                document = json.loads(inventory.read_text())
                document.update(change)
                inventory.write_text(json.dumps(document))
                with patch.object(builder.subprocess, "run") as execute:
                    with self.assertRaisesRegex(ValueError, "does not match"):
                        builder.verify_runtime(output, "1.2.3")
                execute.assert_not_called()

    def test_venv_marker_and_missing_notices_prevent_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = self.runtime(Path(temporary))
            marker = output / "pyvenv.cfg"
            marker.write_text("home = /opt/hostedtoolcache/Python/3.14\n")
            with patch.object(builder.subprocess, "run") as execute:
                with self.assertRaisesRegex(ValueError, "virtual environment"):
                    builder.verify_runtime(output, "1.2.3")
                execute.assert_not_called()
            marker.unlink()
            (output / "PYTHON-LICENSE.txt").unlink()
            info = {"python": "3.14.9", "implementation": "CPython", "frozen": True,
                    "app_version": "1.2.3"}
            with patch.object(builder.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(info))):
                with self.assertRaisesRegex(ValueError, "notices missing: PYTHON-LICENSE"):
                    builder.verify_runtime(output, "1.2.3")

    def test_diagnostic_crash_or_incorrect_runtime_never_passes_verification(self):
        info = {"python": "3.14.9", "implementation": "CPython", "frozen": True,
                "app_version": "1.2.3"}
        for change in ({"python": "3.15.0"}, {"implementation": "PyPy"}, {"app_version": "dev"}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary:
                output = self.runtime(Path(temporary))
                with patch.object(builder.subprocess, "run", return_value=SimpleNamespace(stdout=json.dumps(info | change))):
                    with self.assertRaisesRegex(ValueError, "incorrect frozen runtime"):
                        builder.verify_runtime(output, "1.2.3")
        with tempfile.TemporaryDirectory() as temporary:
            output = self.runtime(Path(temporary))
            with patch.object(builder.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "runtime")):
                with self.assertRaises(subprocess.CalledProcessError):
                    builder.verify_runtime(output, "1.2.3")

    def test_nonempty_output_is_not_overwritten_even_with_valid_build_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            sentinel = output / "previous-runtime"
            sentinel.write_bytes(b"working release")
            with patch.object(builder, "check_environment"), patch.object(builder.subprocess, "run") as execute:
                with self.assertRaisesRegex(ValueError, "refusing to replace"):
                    builder.build(output, "1.2.3")
            self.assertEqual(sentinel.read_bytes(), b"working release")
            execute.assert_not_called()

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


class BuildEnvironmentTests(unittest.TestCase):
    def test_only_target_linux_cpython_314_is_accepted(self):
        for system, implementation, version in (("Darwin", "cpython", (3, 14)),
                ("Windows", "cpython", (3, 14)), ("Linux", "pypy", (3, 14)),
                ("Linux", "cpython", (3, 11)), ("Linux", "cpython", (3, 15))):
            with self.subTest(system=system, implementation=implementation, version=version), \
                    patch.object(builder.platform, "system", return_value=system), \
                    patch.object(sys.implementation, "name", implementation), \
                    patch.object(sys, "version_info", version), patch.object(builder.metadata, "version") as metadata_version:
                with self.assertRaisesRegex(ValueError, "CPython 3.14"):
                    builder.check_environment()
                metadata_version.assert_not_called()

    def test_packager_pin_and_glibc_must_be_verified_before_freezing(self):
        with patch.object(builder.platform, "system", return_value="Linux"), \
                patch.object(sys.implementation, "name", "cpython"), patch.object(sys, "version_info", (3, 14)):
            with patch.object(builder.metadata, "version", return_value="6.16.0"):
                with self.assertRaisesRegex(ValueError, "PyInstaller 6.22.3"):
                    builder.check_environment()
            with patch.object(builder.metadata, "version", return_value="6.22.3") as pin:
                for libc in (("musl", "1.2.5"), ("glibc", ""), ("glibc", "2.35-custom")):
                    with self.subTest(libc=libc), patch.object(builder.platform, "libc_ver", return_value=libc):
                        with self.assertRaisesRegex(ValueError, "glibc"):
                            builder.check_environment()
                with patch.object(builder.platform, "libc_ver", return_value=("glibc", "2.35")):
                    builder.check_environment()
                pin.assert_called_with("pyinstaller")


class RuntimeNoticesTests(unittest.TestCase):
    def test_notices_preserve_colliding_license_names_and_omit_installation_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source", root / "runtime"
            output.mkdir()
            files = {"one/LICENSE": "first license", "two/LICENSE": "second license",
                     "demo.dist-info/licenses/NOTICE": "third party notice",
                     "direct_url.json": '{"url":"private-build-path"}', "module.py": "code"}
            for name, content in files.items():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
            (source / "LICENSE").write_text("project GPL")
            python = root / "python"
            python.mkdir()
            (python / "LICENSE.txt").write_text("Python redistribution license")
            distributions = [SimpleNamespace(metadata={"Name": "Zebra"}, version="2.0",
                files=[*(Path(name) for name in files), Path("missing/LICENSE")],
                locate_file=lambda item: source / item),
                SimpleNamespace(metadata={"Name": "alpha"}, version="1.0", files=None)]
            with patch.object(builder, "ROOT", source), patch.object(sys, "base_prefix", str(python)), \
                    patch.object(builder.metadata, "distributions", return_value=distributions):
                components = builder.copy_notices(output)
            self.assertEqual([item["name"] for item in components], ["alpha", "Zebra"])
            self.assertEqual({path.read_text() for path in (output / "THIRD-PARTY-LICENSES").rglob("*") if path.is_file()},
                             {"first license", "second license", "third party notice"})
            self.assertEqual((output / "PYTHON-LICENSE.txt").read_text(), "Python redistribution license")
            self.assertEqual((output / "LICENSE").read_text(), "project GPL")
            self.assertFalse(any("direct_url" in str(path) for path in output.rglob("*")))

    def test_python_license_fallbacks_work_and_missing_license_blocks_distribution(self):
        for location in ("stdlib/LICENSE.txt", "python/share/doc/python3.14/copyright", None):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "LICENSE").write_text("project GPL")
                output = root / "runtime"
                output.mkdir()
                if location:
                    path = root / location
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("redistribution terms")
                with patch.object(builder, "ROOT", root), patch.object(sys, "base_prefix", str(root / "python")), \
                        patch.object(builder.sysconfig, "get_path", return_value=str(root / "stdlib")), \
                        patch.object(builder.metadata, "distributions", return_value=[]):
                    if location:
                        self.assertEqual(builder.copy_notices(output), [])
                        self.assertEqual((output / "PYTHON-LICENSE.txt").read_text(), "redistribution terms")
                    else:
                        with self.assertRaisesRegex(ValueError, "Python LICENSE.txt is missing"):
                            builder.copy_notices(output)
                        self.assertFalse((output / "LICENSE").exists())


class RuntimeCliTests(unittest.TestCase):
    def test_build_and_verify_modes_do_not_dispatch_each_other(self):
        for verify in (False, True):
            with self.subTest(verify=verify), patch.object(builder, "build") as build, \
                    patch.object(builder, "verify_runtime") as check:
                arguments = ["--output", "payload", "--version", "1.2.3"]
                if verify:
                    arguments.append("--verify-only")
                builder.main(arguments)
                selected, unused = (check, build) if verify else (build, check)
                selected.assert_called_once_with(Path("payload"), "1.2.3")
                unused.assert_not_called()

    def test_invalid_release_is_rejected_before_build_or_verify(self):
        for version in ("dev", "1.2", "1.2.3;touch bad", "1.2.3rc1"):
            with self.subTest(version=version), patch.object(builder, "build") as build, \
                    patch.object(builder, "verify_runtime") as verify, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    builder.main(["--output", "payload", "--version", version])
                self.assertEqual(error.exception.code, 2)
                build.assert_not_called()
                verify.assert_not_called()

    def test_command_line_help_never_starts_freezing(self):
        with patch.object(sys, "argv", ["build_linux_runtime.py", "--help"]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as error:
                runpy.run_path(str(ROOT / "scripts/build_linux_runtime.py"), run_name="__main__")
        self.assertEqual(error.exception.code, 0)
        self.assertIn("--verify-only", output.getvalue())


if __name__ == "__main__":
    unittest.main()
