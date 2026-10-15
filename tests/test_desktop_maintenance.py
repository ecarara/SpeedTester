# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native lifecycle with mocked OS adapters and real encrypted SQLite files."""
import hashlib
import json
import os
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from speedtester_protocol.installation import protected_queue
from speedtester_protocol.native_services import (Layout, MARKER, BOOTSTRAP, native_layout,
    system_service_unit, launch_daemon, verify_bundle, verify_database, read_request, native_operation)


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "download"
        self.source.mkdir()
        (self.source / "SpeedTesterClient").write_text("Synthetic binary, never executed")
        self.manifest()
        self.layout = Layout("Linux", self.root / "installed/runtime", self.root / "managed-state",
            self.root / "installed/runtime/SpeedTesterClient", self.root / "service.definition", "synthetic-service")
        self.key = "a" * 64
        self.request = {"operation": "install", "control_key": self.key, "purge": False}
        self.identity = SimpleNamespace(pw_uid=getattr(os, "getuid", lambda: 1000)(), pw_gid=getattr(os, "getgid", lambda: 1000)())
        for name, options in {
            "native_layout": {"return_value": self.layout}, "bundle_root": {"return_value": self.source},
            "require_admin": {}, "trusted_parent": {}, "stop_service": {}, "register_service": {},
            "start_service": {}, "remove_service": {}, "windows_acl": {},
            "provision_identity": {"return_value": self.identity},
        }.items():
            mock = patch("speedtester_protocol.native_services." + name, **options)
            setattr(self, "mock_" + name, mock.start())
            self.addCleanup(mock.stop)
        chown = patch("os.chown", create=True)
        chown.start();self.addCleanup(chown.stop)

    def manifest(self):
        files = {path.relative_to(self.source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.source.rglob("*") if path.is_file() and path.name != "bundle-manifest.json"}
        (self.source / "bundle-manifest.json").write_text(json.dumps({"format": MARKER, "files": files}))

    def install(self):
        result = native_operation(self.request)
        self.assertTrue(result["ok"])
        self.assertFalse(result["measurements_enabled"])
        return protected_queue(self.layout.state / "queue")

    def test_install_and_repair_preserve_keys_signed_records_pending_queue_and_pause_schedule(self):
        queue = self.install()
        queue.state("installation", {"possession_private": "synthetic-key", "origin": "https://server.example"})
        queue.state("desktop:measurements_enabled", True)
        record = {"id": "synthetic-record", "signature": "synthetic-signature", "value": 100}
        queue.put(record, "synthetic-destination")
        key = (queue.directory / "storage.key").read_bytes()
        installed = queue.state("installation")
        native_operation({**self.request, "operation": "repair"})
        reloaded = protected_queue(queue.directory)
        self.assertEqual(reloaded.pending("synthetic-destination"), [record])
        self.assertEqual(reloaded.state("installation"), installed)
        self.assertEqual((queue.directory / "storage.key").read_bytes(), key)
        self.assertFalse(reloaded.state("desktop:measurements_enabled"))
        backups = list((self.layout.state / "backups").iterdir())
        self.assertEqual(len(backups), 1)
        verify_database(backups[0])
        self.assertEqual(self.mock_start_service.call_count, 2)

    def test_corruption_or_missing_key_stops_repair_without_resetting_data(self):
        queue = self.install()
        queue.state("important", {"value": "preserve"})
        key = queue.directory / "storage.key"
        key.unlink()
        before = queue.path.read_bytes()
        with self.assertRaises(ValueError):native_operation({**self.request, "operation": "repair"})
        self.assertEqual(queue.path.read_bytes(), before)
        self.assertFalse(key.exists())
        self.assertEqual(self.mock_start_service.call_count, 1)

    def test_authenticated_ciphertext_damage_is_rejected_without_rewriting_it(self):
        queue = self.install()
        queue.state("important", {"value": "preserve"})
        with queue.connection() as connection:
            connection.execute("UPDATE state SET value=? WHERE key=?", (b"x" * 64, "important"))
        before = queue.path.read_bytes()
        with self.assertRaises(Exception):native_operation({**self.request, "operation": "repair"})
        self.assertEqual(queue.path.read_bytes(), before)

    def test_uninstall_preserves_data_then_reinstall_and_explicit_purge_remove_it(self):
        queue = self.install()
        queue.put({"id": "retained", "value": 1}, "synthetic")
        result = native_operation({**self.request, "operation": "uninstall"})
        self.assertTrue(result["data_preserved"])
        self.assertEqual(result["central_revocation"], "not_requested")
        self.assertTrue(queue.path.exists())
        self.assertFalse(self.layout.runtime.exists())
        native_operation(self.request)
        self.assertEqual(protected_queue(queue.directory).pending("synthetic"), [{"id": "retained", "value": 1}])
        result = native_operation({**self.request, "operation": "uninstall", "purge": True})
        self.assertFalse(result["data_preserved"])
        self.assertFalse(self.layout.state.exists())
        self.assertTrue(self.source.exists())

    def test_wrong_control_key_and_arbitrary_paths_or_actions_are_not_accepted(self):
        self.install()
        with self.assertRaises(PermissionError):native_operation({**self.request, "control_key": "b" * 64})
        path = self.root / "request.json"
        path.write_text(json.dumps({**self.request, "runtime": "/somewhere"}));path.chmod(0o600)
        with self.assertRaises(ValueError):read_request(path)
        path.write_text(json.dumps({**self.request, "operation": "execute"}))
        with self.assertRaises(ValueError):read_request(path)
        self.assertTrue(self.layout.runtime.exists())

    def test_bundle_mismatch_extra_files_and_failed_start_restore_previous_runtime(self):
        queue = self.install()
        old = self.layout.executable.read_bytes()
        (self.source / "SpeedTesterClient").write_text("Changed binary")
        with self.assertRaises(ValueError):verify_bundle(self.source)
        self.manifest()
        self.mock_start_service.side_effect = [RuntimeError("synthetic failure"), None]
        with self.assertRaises(RuntimeError):native_operation({**self.request, "operation": "repair"})
        self.assertEqual(self.layout.executable.read_bytes(), old)
        self.assertTrue(queue.path.exists())
        self.assertFalse(self.layout.runtime.with_name("runtime.previous").exists())

    def test_system_definitions_are_boot_services_not_user_login_agents(self):
        linux = native_layout("Linux")
        unit = system_service_unit(linux)
        self.assertIn("WantedBy=multi-user.target", unit)
        self.assertIn("User=speedtester-client", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("ProtectHome=true", unit)
        self.assertNotIn("User=root", unit)
        macos = native_layout("Darwin")
        definition = plistlib.loads(launch_daemon(macos))
        self.assertTrue(definition["RunAtLoad"])
        self.assertEqual(definition["UserName"], "_speedtester")
        self.assertIn("LaunchDaemons", str(macos.definition))
        self.assertEqual(definition["ProgramArguments"][-1], "--agent")
        self.assertNotIn("control_key", unit + json.dumps(definition))


if __name__ == "__main__":
    unittest.main()
