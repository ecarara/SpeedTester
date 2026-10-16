# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Portable desktop protocol tests: synthetic signatures, no measurement runner."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock, patch
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from speedtester_protocol.cli import exclusive
from speedtester_protocol.client import ProtocolError
from speedtester_protocol.crypto import b64, public_bytes, sign, verify, check_dpop
from speedtester_protocol.desktop_service import DesktopEngine, CONFIGURATION, ENABLED
from speedtester_protocol.desktop_controller import DesktopController, PreviewController
from speedtester_protocol.desktop_text import TEXT
from speedtester_protocol.installation import protected_queue
from speedtester_protocol.local_control import Authenticator, ControlServer, ControlClient, serve_in_thread
from speedtester_protocol.models import Pairing, PairingRequest, CredentialBundle


def configuration(contribute=True):
    return {"origin": "https://server.example", "profile": {"version": 1, "operator": "Synthetic provider",
        "country_code": "ZZ", "region": "Test region", "city": "Test city", "access_type": "fiber", "link_type": "ethernet"},
        "timezone": "America/Sao_Paulo", "contribute": contribute}


class SignedProvider:
    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        self.calls = []
        self.approved = False
        self.pairing = None
        self.identity = None
        self.client_id = str(uuid4())
        self.last_bundle = None
        self.blocked = None
        self.target_available = True

    def bundle(self, request_id):
        now = int(time.time())
        bundle = CredentialBundle(client_id=self.client_id, access_token=secrets.token_urlsafe(32),
            refresh_token=secrets.token_urlsafe(32), expires_at=now + 900, refresh_expires_at=now + 30 * 86400,
            nonce=secrets.token_urlsafe(32), possession_key=self.identity, request_id=request_id)
        self.last_bundle = bundle
        return sign(bundle.model_dump(), self.key, "credentials-v1")

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path))
        if path == "/.well-known/speedtester-server":
            return 200, {}, {"protocol_version": "1", "origin": "https://server.example", "signing_key": b64(public_bytes(self.key))}
        if path == "/api/v1/pairings":
            request = PairingRequest.model_validate(body["payload"])
            from speedtester_protocol.crypto import unb64
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            self.possession = Ed25519PublicKey.from_public_bytes(unb64(request.possession_key))
            verify(body, self.possession, "pairing-request-v1")
            self.identity = request.possession_key
            self.pairing = Pairing(request_id=request.request_id, device_code=secrets.token_urlsafe(32),
                user_code="ABCDE-F2345", verification_uri="https://server.example/pair", expires_at=int(time.time()) + 600,
                interval=5, nonce=secrets.token_urlsafe(32), possession_key=request.possession_key)
            return 201, {}, sign(self.pairing.model_dump(), self.key, "pairing-v1")
        if path == "/api/v1/pairings/token":
            if not self.approved:
                return 400, {}, {"code": "authorization_pending"}
            check_dpop(headers["DPoP"], self.possession, method, "https://server.example" + path,
                self.pairing.device_code, self.pairing.nonce)
            return 200, {}, self.bundle(self.pairing.request_id)
        if path == "/api/v1/test-target":
            if not self.target_available:
                return 503, {}, {"code":"test_target_unavailable"}
            from speedtester_protocol.targets import TestTarget, target_identifier
            now=int(time.time())
            target=TestTarget(request_id=body["request_id"],client_id=self.client_id,
                host="target.example",port=5201,target_scope="unconfirmed",
                target_id=target_identifier("target.example",5201,"unconfirmed"),issued_at=now,expires_at=now+300)
            return 200, {}, sign(target.model_dump(),self.key,"test-target-v1")
        if path == "/api/v1/credentials/rotate":
            if self.blocked:
                return 403, {}, {"code": self.blocked}
            check_dpop(headers["DPoP"], self.possession, method, "https://server.example" + path,
                self.last_bundle.refresh_token, self.last_bundle.nonce)
            return 200, {}, self.bundle(body["request_id"])
        raise AssertionError("No measurement endpoints are allowed in these tests")


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.queue = protected_queue(self.root / "state")
        self.provider = SignedProvider()
        self.runner = Mock(side_effect=AssertionError("No measurements"))
        self.engine = DesktopEngine(self.queue, transport=self.provider, runner=self.runner)

    def pair(self):
        self.assertTrue(self.engine.dispatch("configure", configuration())["ok"])
        response = self.engine.dispatch("pair", {})
        self.assertEqual(response["pairing"]["user_code"], "ABCDE-F2345")
        self.assertEqual(self.engine.tick(), "authorization_pending")
        self.provider.approved = True
        self.engine.next_poll = 0
        self.assertEqual(self.engine.tick(), "paired")

    def test_unconfigured_and_explicit_opt_out_never_contact_the_server(self):
        self.assertEqual(self.engine.tick(), "idle")
        self.assertTrue(self.engine.dispatch("configure", configuration(False))["ok"])
        self.assertEqual(self.engine.tick(), "idle")
        self.assertEqual(self.engine.dispatch("pair", {})["code"], "contribution_not_selected")
        self.assertEqual(self.engine.dispatch("enable", {})["code"], "pairing_required")
        self.assertEqual(self.provider.calls, [])
        self.assertIsNone(self.queue.state("installation"))
        self.runner.assert_not_called()

    def test_status_is_read_only_and_keeps_activation_problem_until_successful_retry(self):
        self.pair()
        calls=list(self.provider.calls)
        with self.queue.connection() as conn:
            before=conn.execute('SELECT key,value FROM state ORDER BY key').fetchall()
        status=self.engine.dispatch('status',{})
        self.assertGreater(status['observed_at'],0)
        self.assertEqual(status['accepted'],0)
        self.assertIsNone(status['last_attempt_at'])
        with self.queue.connection() as conn:
            self.assertEqual(before,conn.execute('SELECT key,value FROM state ORDER BY key').fetchall())
        self.assertEqual(self.provider.calls,calls)
        self.provider.target_available=False
        self.assertEqual(self.engine.dispatch('enable',{})['code'],'test_target_unavailable')
        restored=DesktopEngine(protected_queue(self.queue.directory),transport=self.provider,runner=self.runner)
        self.assertEqual(restored.status()['problem']['code'],'test_target_unavailable')
        self.provider.target_available=True
        self.assertTrue(restored.dispatch('enable',{})['measurements_enabled'])
        self.assertIsNone(restored.status()['problem'])
        self.runner.assert_not_called()

    def test_pairing_uses_signed_sdk_and_persists_tokens_without_starting_schedule(self):
        self.pair()
        self.assertTrue(self.engine.status()["paired"])
        self.assertFalse(self.engine.status()["measurements_enabled"])
        self.assertGreater(self.queue.state("next_due"), int(time.time()))
        bundle = self.provider.last_bundle
        raw = self.queue.path.read_bytes()
        self.assertNotIn(bundle.access_token.encode(), raw)
        self.assertNotIn(bundle.refresh_token.encode(), raw)
        status = json.dumps(self.engine.status())
        self.assertNotIn(bundle.access_token, status)
        self.assertNotIn(bundle.refresh_token, status)
        self.assertNotIn("device_code", status)
        restored = DesktopEngine(protected_queue(self.queue.directory), transport=self.provider, runner=self.runner)
        self.assertTrue(restored.status()["paired"])
        self.runner.assert_not_called()

    def test_pairing_needs_no_target_and_unavailable_target_prevents_activation(self):
        self.provider.target_available=False
        self.pair()
        self.assertNotIn("/api/v1/test-target",[path for _,path in self.provider.calls])
        self.assertNotIn("host",self.queue.state("installation"))
        self.assertEqual(self.queue.state("installation")["target_mode"],"automatic")
        self.assertEqual(self.engine.dispatch("enable",{})["code"],"test_target_unavailable")
        self.assertFalse(self.queue.state(ENABLED))
        self.assertTrue(self.engine.status()["paired"])
        self.runner.assert_not_called()

    def test_upgrade_discards_old_manual_target_and_keeps_schedule_paused(self):
        self.pair()
        installed=self.queue.state("installation")
        identity=installed["possession_private"]
        installed.pop("target_mode")
        installed.update(host="old-user-target.example",port=9999)
        self.queue.state("installation",installed)
        self.queue.state(ENABLED,True)
        restored=DesktopEngine(self.queue,transport=self.provider,runner=self.runner)
        upgraded=self.queue.state("installation")
        self.assertEqual(upgraded["target_mode"],"automatic")
        self.assertEqual(upgraded["possession_private"],identity)
        self.assertNotIn("host",upgraded)
        self.assertNotIn("port",upgraded)
        self.assertFalse(restored.status()["measurements_enabled"])
        self.assertTrue(restored.status()["paired"])
        self.runner.assert_not_called()

    def test_pending_code_is_recovered_without_contacting_server_or_rotating_authorization(self):
        self.engine.dispatch('configure',configuration())
        first=self.engine.dispatch('pair',{})
        pending=self.engine.pairing
        calls=list(self.provider.calls)
        recovered=self.engine.dispatch('pair',{})
        self.assertEqual(first['pairing'],recovered['pairing'])
        self.assertIs(self.engine.pairing,pending)
        self.assertEqual(self.provider.calls,calls)
        self.assertFalse(recovered['measurements_enabled'])
        self.runner.assert_not_called()

    def test_expired_pairing_requires_explicit_restart_and_cancel_stops_polling(self):
        self.engine.dispatch("configure", configuration())
        self.engine.dispatch("pair", {})
        self.engine.pairing = self.engine.pairing.model_copy(update={"expires_at": 1})
        self.assertEqual(self.engine.tick(), "pairing_expired")
        before = len(self.provider.calls)
        self.engine.tick()
        self.assertEqual(len(self.provider.calls), before)
        self.engine.dispatch("pair", {})
        self.engine.dispatch("cancel_pairing", {})
        before = len(self.provider.calls)
        self.engine.tick()
        self.assertEqual(len(self.provider.calls), before)

    def test_pause_and_disconnect_preserve_identity_and_never_execute_a_runner(self):
        self.pair()
        installed = self.queue.state("installation")
        self.assertTrue(self.engine.dispatch("enable", {})["measurements_enabled"])
        self.assertEqual(self.engine.tick(), "waiting")
        self.engine.dispatch("pause", {})
        self.assertEqual(self.engine.tick(), "paused")
        self.engine.dispatch("disconnect", {})
        before = len(self.provider.calls)
        self.assertEqual(self.engine.tick(), "idle")
        self.assertEqual(len(self.provider.calls), before)
        self.assertEqual(self.queue.state("installation"), installed)
        self.runner.assert_not_called()

    def test_suspended_or_revoked_accounts_cannot_be_enabled_or_repaired_by_repairing_pairing(self):
        self.pair()
        for code in ("account_suspended", "client_revoked", "consent_withdrawn", "legal_acceptance_required"):
            self.provider.blocked = code
            self.assertFalse(self.engine.dispatch("enable", {})["ok"])
            self.assertFalse(self.queue.state(ENABLED))
            self.assertFalse(self.engine.dispatch("pair", {})["ok"])
        self.runner.assert_not_called()

    def test_legacy_interval_migration_pauses_and_preserves_identity_and_schedule(self):
        self.pair()
        original=dict(self.queue.state("installation"))
        original.pop("schedule")
        original["interval"]=3600
        # Simulate a pre-schedule installation, which has no persisted plans.
        with self.queue.connection() as conn:
            conn.execute("DELETE FROM state WHERE key LIKE ?",("schedule:%",))
        self.queue.state("installation",original)
        old_config=configuration();old_config.pop("timezone");old_config["interval_hours"]=1
        self.queue.state(CONFIGURATION,old_config)
        self.queue.state(ENABLED,True)
        self.queue.state("retained-evidence",{"value":"unchanged"})
        self.provider.calls.clear()
        migrated=DesktopEngine(self.queue,transport=self.provider,runner=self.runner)
        installed=self.queue.state("installation")
        self.assertEqual({k:v for k,v in installed.items() if k!="schedule"},{k:v for k,v in original.items() if k!="interval"})
        self.assertFalse(migrated.status()["measurements_enabled"])
        self.assertTrue(migrated.status()["paired"])
        self.assertNotIn("interval_hours",migrated.status()["configuration"])
        self.assertEqual(self.queue.state("retained-evidence"),{"value":"unchanged"})
        from speedtester_protocol.schedule import DailySchedule
        before=DailySchedule(self.queue,installed["schedule"]).refresh(int(time.time()))
        reopened=DesktopEngine(protected_queue(self.queue.directory),transport=self.provider,runner=self.runner)
        after=DailySchedule(reopened.queue,installed["schedule"]).refresh(int(time.time()))
        self.assertEqual(before,after)
        self.assertEqual([len(day["slots"]) for day in after],[8,8])
        self.assertEqual(self.provider.calls,[])
        self.runner.assert_not_called()

    def test_changed_server_identity_is_refused_and_profile_versions_are_stable(self):
        self.pair()
        changed = configuration()
        changed["profile"]["city"] = "Other city"
        self.engine.dispatch("configure", changed)
        self.assertEqual(self.queue.state("installation")["profile"]["version"], 2)
        self.engine.dispatch("configure", changed)
        self.assertEqual(self.queue.state("installation")["profile"]["version"], 2)
        self.provider.key = Ed25519PrivateKey.generate()
        self.assertEqual(self.engine.dispatch("pair", {})["code"], "installation_server_changed")

    def test_storage_limit_never_requests_new_grants_or_drops_pending_records(self):
        self.pair()
        self.engine.dispatch("enable", {})
        self.queue.state("next_due", 1)
        with patch("speedtester_protocol.desktop_service.MAX_DATABASE_BYTES", 0):
            self.assertEqual(self.engine.tick(), "storage_limit")
        self.runner.assert_not_called()
        self.assertFalse(any("measurement-grants" in path for _, path in self.provider.calls))

    def test_status_remains_available_while_the_agent_is_busy(self):
        locked, release = threading.Event(), threading.Event()
        def busy():
            with self.engine.lock:
                locked.set()
                release.wait(5)
        worker = threading.Thread(target=busy)
        worker.start()
        try:
            self.assertTrue(locked.wait(2))
            self.assertTrue(self.engine.dispatch("status", {}).get("busy"))
            self.assertEqual(self.engine.dispatch("pair", {})["code"], "local_busy")
        finally:
            release.set()
            worker.join(3)

    def test_queue_reads_are_bounded_and_a_missing_key_is_not_regenerated(self):
        for index in range(270):
            self.queue.put({"id": str(index), "value": index}, "synthetic")
        self.assertEqual(len(self.queue.pending("synthetic")), 256)
        self.assertEqual(len(self.queue.pending("synthetic", limit=10)), 10)
        with self.assertRaises(ValueError):
            self.queue.pending("synthetic", limit=0)
        key = self.queue.directory / "storage.key"
        key.unlink()
        with self.assertRaises(ValueError):
            protected_queue(self.queue.directory)
        self.assertFalse(key.exists())

    def test_process_lock_cannot_be_acquired_by_a_second_process(self):
        command = [sys.executable, "-c", "from pathlib import Path;from speedtester_protocol.installation import protected_queue;from speedtester_protocol.cli import exclusive;import sys;\nwith exclusive(protected_queue(Path(sys.argv[1]))): pass", str(self.queue.directory)]
        with exclusive(self.queue):
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
        subprocess.run(command, capture_output=True, timeout=10, check=True)

    def test_all_languages_are_complete_and_preview_does_not_call_network_or_native_tools(self):
        self.assertEqual(set(TEXT), {"pt-BR", "en", "es"})
        for translations in TEXT.values():
            self.assertEqual(set(translations), set(TEXT["pt-BR"]))
            self.assertTrue(all(isinstance(value, str) and value for value in translations.values()))
        with patch("subprocess.run", side_effect=AssertionError("No elevation")), patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("No network")):
            fixture = PreviewController()
            fixture.native("install")
            fixture.call("configure", configuration())
            fixture.call("pair")
        controller = DesktopController(self.root / "control")
        self.assertEqual(DesktopController(self.root / "control").key, controller.key)
        with self.assertRaises(ValueError):
            controller.native("install")

    def test_purge_then_reinstall_in_same_window_creates_a_new_persistent_control_identity(self):
        controller=DesktopController(self.root/'control')
        original=controller.key
        with patch('sys.frozen',True,create=True), patch('platform.system',return_value='Darwin'), \
                patch('subprocess.run',return_value=Mock(returncode=0)):
            controller.native('uninstall',True)
            self.assertFalse(controller.control.exists())
            self.assertIsNone(controller.key)
            controller.native('install')
        self.assertNotEqual(controller.key,original)
        self.assertEqual(DesktopController(self.root/'control').key,controller.key)


class LocalControlTests(unittest.TestCase):
    def setUp(self):
        self.key = secrets.token_bytes(32)

    def test_hmac_tampering_expiry_replay_and_response_binding(self):
        client, server = Authenticator(self.key), Authenticator(self.key)
        request = client.request("status")
        payload = server.authenticate(request)
        self.assertEqual(client.verify_response(payload["nonce"], server.response(payload["nonce"], {"ok": True})), {"ok": True})
        with self.assertRaises(ProtocolError):server.authenticate(request)
        with self.assertRaises(ProtocolError):client.verify_response("different", server.response(payload["nonce"], {"ok": True}))
        changed = client.request("status");changed["payload"]["operation"] = "enable"
        with self.assertRaises(ProtocolError):server.authenticate(changed)
        expired = Authenticator(self.key, clock=lambda: time.time() - 100).request("status")
        with self.assertRaises(ProtocolError):server.authenticate(expired)
        for _ in range(255):server.authenticate(client.request("status"))
        with self.assertRaises(ProtocolError):server.authenticate(client.request("status"))
        with self.assertRaises(ProtocolError):server.authenticate(request)

    def test_real_loopback_requests_reject_browser_origins_wrong_keys_and_large_bodies(self):
        dispatch = Mock(return_value={"ok": True, "service": "running"})
        server = ControlServer(self.key, dispatch, port=0)
        thread = serve_in_thread(server)
        try:
            port = server.server_address[1]
            self.assertEqual(ControlClient(self.key, port).call("status")["service"], "running")
            self.assertEqual(dispatch.call_count, 1)
            with self.assertRaises(urllib.error.HTTPError):ControlClient(secrets.token_bytes(32), port).call("enable")
            url = f"http://127.0.0.1:{port}/control/v1"
            request = urllib.request.Request(url, data=b"{}", headers={"Origin": "https://attacker.example"})
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request, timeout=3)
            request = urllib.request.Request(url, data=b"x" * 20000)
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(request, timeout=3)
            self.assertEqual(dispatch.call_count, 1)
        finally:
            server.shutdown();server.server_close();thread.join(3)

    def test_agent_process_outlives_a_control_client_without_pairing_or_measurements(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = str(Path(temporary).resolve() / "state")
            with socket.socket() as reserve:
                reserve.bind(("127.0.0.1", 0));port = reserve.getsockname()[1]
            command = [sys.executable, "-c", "from speedtester_protocol.desktop_service import run_service;import sys;run_service(sys.argv[1],bytes.fromhex(sys.argv[2]),port=int(sys.argv[3]))", state, self.key.hex(), str(port)]
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        raise AssertionError("Idle service exited: " + process.stderr.read().decode(errors="replace"))
                    try:
                        response = ControlClient(self.key, port, timeout=1).call("status")
                        break
                    except OSError:
                        if time.monotonic() > deadline:raise
                        time.sleep(.1)
                self.assertFalse(response["paired"])
                self.assertFalse(response["measurements_enabled"])
                del response
                self.assertEqual(ControlClient(self.key, port).call("status")["service"], "running")
            finally:
                process.terminate()
                process.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()


class IdentificationTests(unittest.TestCase):
    def test_version_matches_distribution_and_diagnostics_omit_operational_state(self):
        import tomllib
        from speedtester_protocol import version
        project=tomllib.loads(Path(__file__).resolve().parents[1].joinpath('pyproject.toml').read_text())
        self.assertEqual(version.CLIENT_VERSION,project['project']['version'])
        with patch.object(version,'BUILD_REVISION','a'*40):
            info=version.diagnostic_text({'client_version':version.CLIENT_VERSION,'build_revision':'a'*40,
                'access_token':'never-copy-this','configuration':{'host':'private.internal'}})
            self.assertIn(version.CLIENT_VERSION,info)
            self.assertIn('a'*40,info)
            self.assertNotIn('never-copy-this',info)
            self.assertNotIn('private.internal',info)
        with self.assertRaises(ValueError):version.set_build_revision('not-a-revision')

    def test_linux_locale_payload_does_not_change_keyboard_ime_or_language(self):
        from speedtester_protocol import input_methods
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'x11/locale').mkdir(parents=True);(root/'x11/modules').mkdir()
            original={'LANG':'pt_BR.UTF-8','XMODIFIERS':'@im=fcitx','XKB_DEFAULT_LAYOUT':'br'}
            with patch.dict(os.environ,original,clear=True),patch.object(sys,'platform','linux'),patch.object(sys,'frozen',True,create=True),patch.object(sys,'_MEIPASS',str(root),create=True):
                input_methods.configure_input_methods()
                self.assertEqual(os.environ['XLOCALEDIR'],str(root/'x11/locale'))
                self.assertEqual(os.environ['XLOCALELIBDIR'],str(root/'x11/modules'))
                for key,value in original.items():self.assertEqual(os.environ[key],value)
                os.environ['XLOCALEDIR']='/explicit-user-config'
                input_methods.configure_input_methods()
                self.assertEqual(os.environ['XLOCALEDIR'],'/explicit-user-config')
