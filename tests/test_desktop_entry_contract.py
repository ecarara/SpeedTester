# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Entry-point contracts with synthetic configuration and simulated OS adapters."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from speedtester_protocol import desktop_entry as entry
from speedtester_protocol import desktop_links
from speedtester_protocol.native_services import BOOTSTRAP, MARKER


class DesktopEntryTests(unittest.TestCase):
    def test_frozen_tls_uses_packaged_ca_but_preserves_admin_overrides(self):
        with patch.object(sys, 'frozen', True, create=True), patch.dict(os.environ, {}, clear=True), \
                patch('certifi.where', return_value='/fixture/ca.pem'):
            entry.configure_tls()
            self.assertEqual(os.environ['SSL_CERT_FILE'], '/fixture/ca.pem')
        for key in ('SSL_CERT_FILE', 'SSL_CERT_DIR'):
            with self.subTest(key=key), patch.object(sys, 'frozen', True, create=True), \
                    patch.dict(os.environ, {key: '/admin/ca'}, clear=True), patch('certifi.where') as lookup:
                entry.configure_tls()
                lookup.assert_not_called()

    def test_agent_validates_bootstrap_and_uses_a_fixed_runtime_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bootstrap = root / BOOTSTRAP
            layout = SimpleNamespace(state=root, runtime=root, executable=root / 'client')
            stop = Mock()
            with patch.object(entry, 'native_layout', return_value=layout), patch.object(entry.os, 'chdir') as chdir, \
                    patch.object(entry.signal, 'signal'), patch.dict(os.environ, {}, clear=True), \
                    patch('speedtester_protocol.desktop_service.run_service', return_value='stopped') as run:
                for configuration, message in (({'format': 'wrong'}, 'invalid_service_configuration'),
                        ({'format': MARKER, 'control_key': 'ab'}, 'invalid_control_key')):
                    bootstrap.write_text(json.dumps(configuration))
                    with self.assertRaisesRegex(ValueError, message):
                        entry.agent_main(stop)
                bootstrap.write_text('x' * 4097)
                with self.assertRaisesRegex(ValueError, 'invalid_service_configuration'):
                    entry.agent_main(stop)
                bootstrap.write_text(json.dumps({'format': MARKER, 'control_key': 'ab' * 32}))
                self.assertEqual(entry.agent_main(stop), 'stopped')
                run.assert_called_once_with(root / 'queue', bytes.fromhex('ab' * 32), stop)
                chdir.assert_called_once_with(root)
                self.assertTrue(os.environ['PATH'].startswith(str(root / 'tools')))

    def test_native_helper_exit_codes_and_diagnostics_do_not_disclose_requests(self):
        for reboot, expected in ((False, 0), (True, 10)):
            with self.subTest(reboot=reboot), patch('speedtester_protocol.native_services.read_request', return_value={}), \
                    patch('speedtester_protocol.native_services.native_operation', return_value={'reboot_required': reboot}):
                self.assertEqual(entry.native_helper_main(Path('fixture')), expected)
        with patch('speedtester_protocol.native_services.read_request', side_effect=ValueError('PRIVATE_REQUEST_VALUE')), \
                patch.object(entry.os, 'write') as write:
            self.assertEqual(entry.native_helper_main(Path('fixture')), 20)
            diagnostic = json.loads(write.call_args.args[1])
            self.assertEqual(diagnostic['code'], 'native_operation_failed')
            self.assertNotIn('PRIVATE_REQUEST_VALUE', str(diagnostic))
        with patch('speedtester_protocol.native_services.read_request', side_effect=ValueError), \
                patch.object(entry.os, 'write', side_effect=OSError):
            self.assertEqual(entry.native_helper_main(Path('fixture')), 20)

    def test_cli_modes_dispatch_without_starting_a_service_or_measurement(self):
        with patch.object(entry, 'agent_main', return_value=7):
            self.assertEqual(entry.main(['--agent']), 7)
        module = SimpleNamespace(dispatch_service=Mock(return_value=8))
        with patch.dict(sys.modules, {'speedtester_protocol.windows_service': module}):
            self.assertEqual(entry.main(['--windows-service']), 8)
        with patch.object(entry, 'native_helper_main', return_value=10):
            self.assertEqual(entry.main(['--native-helper', 'fixture']), 10)
        with patch('speedtester_protocol.input_methods.configure_input_methods'), \
                patch('speedtester_protocol.desktop_gui.Installer') as installer, \
                patch.object(entry, 'configure_tls'), patch.object(entry, 'smoke_browser_probe') as probe:
            self.assertEqual(entry.main(['--preview']), 0)
            installer.return_value.mainloop.assert_called_once()
            self.assertEqual(entry.main(['--ui-smoke']), 0)
            installer.return_value.smoke_test.assert_called_once()
            probe.assert_called_once()

    def test_browser_probe_rejects_non_ci_inputs_and_reports_bounded_outcomes(self):
        with patch.dict(os.environ, {}, clear=True):
            entry.smoke_browser_probe()
        for probe in ('bad', '0/' + 'a' * 32, '65536/' + 'a' * 32):
            environment = {'SPEEDTESTER_BROWSER_PROBE': probe, 'GITHUB_ACTIONS': 'true',
                           'RUNNER_ENVIRONMENT': 'github-hosted'}
            with self.subTest(probe=probe), patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(ValueError, 'invalid_ci_browser_probe'):
                    entry.smoke_browser_probe()
        valid = {'SPEEDTESTER_BROWSER_PROBE': '1234/' + 'a' * 32, 'GITHUB_ACTIONS': 'true',
                 'RUNNER_ENVIRONMENT': 'github-hosted'}
        for failure in (False, True):
            def open_fixture(_url, fail=failure):
                if fail:
                    raise OSError('synthetic')
                return desktop_links.subprocess.run(['fixture']).returncode == 0
            with self.subTest(failure=failure), patch.dict(os.environ, valid, clear=True), \
                    patch.object(desktop_links.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr=b'fixture')), \
                    patch.object(desktop_links, 'open_system_browser', side_effect=open_fixture), \
                    patch.object(entry.os, 'write') as write:
                entry.smoke_browser_probe()
                self.assertLessEqual(max(len(call.args[1]) for call in write.call_args_list), 2100)
