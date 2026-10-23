# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""OS service adapters and CI guards use only temporary paths and fake APIs."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from speedtester_protocol import native_services as native

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import test_native_lifecycle as lifecycle


class NativeAdaptersTests(unittest.TestCase):
    def test_linux_and_macos_registration_start_stop_and_removal(self):
        for system in ('Linux', 'Darwin'):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                layout = native.Layout(system, root / 'runtime', root / 'state', root / 'client', root / 'service', 'fixture')
                with patch.object(native, 'checked', return_value='') as checked, \
                        patch.object(native.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
                    native.register_service(layout)
                    self.assertTrue(layout.definition.is_file())
                    if system == 'Linux':
                        native.start_service(layout)
                        native.stop_service(layout)
                    else:
                        with patch.object(native.subprocess, 'run', side_effect=[SimpleNamespace(returncode=5), SimpleNamespace(returncode=0)]), \
                                patch.object(native.time, 'sleep'):
                            native.start_service(layout)
                        with patch.object(native.subprocess, 'run', side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=0), SimpleNamespace(returncode=1)]), \
                                patch.object(native.time, 'sleep'):
                            native.stop_service(layout)
                    native.remove_service(layout)
                    self.assertFalse(layout.definition.exists())
                    self.assertTrue(checked.called)

    def test_macos_identity_creation_never_reuses_an_occupied_uid(self):
        import pwd
        layout = SimpleNamespace(system='Darwin', user='_fixture')
        identity = SimpleNamespace(pw_uid=498, pw_dir='/var/empty', pw_shell='/usr/bin/false')
        with patch.object(pwd, 'getpwnam', side_effect=[KeyError(), identity]), \
                patch.object(native, 'checked', return_value='existing 499') as checked:
            self.assertIs(native.provision_identity(layout), identity)
            commands = [call.args[0] for call in checked.call_args_list]
            self.assertTrue(any(command[-1] == '498' for command in commands))
        occupied = '\n'.join('fixture ' + str(uid) for uid in range(200, 500))
        with patch.object(native, 'checked', return_value=occupied):
            with self.assertRaisesRegex(ValueError, 'service_identity_unavailable'):
                native._create_posix_identity(layout)

    def test_windows_service_adapter_uses_fixed_identity_and_handles_absent_service(self):
        class ServiceError(Exception):
            def __init__(self, code):
                self.winerror = code
        api = SimpleNamespace(QueryServiceStatus=Mock(return_value=(0, 4)), StopService=Mock(),
            WaitForServiceStatus=Mock(), StartService=Mock(), InstallService=Mock(),
            ChangeServiceConfig=Mock(), RemoveService=Mock())
        modules = {'pywintypes': SimpleNamespace(error=ServiceError), 'win32serviceutil': api,
                   'win32service': SimpleNamespace(SERVICE_STOPPED=1, SERVICE_AUTO_START=2)}
        layout = SimpleNamespace(system='Windows', user='synthetic-service', executable=Path('fixture.exe'))
        with patch.dict(sys.modules, modules):
            native.stop_service(layout)
            api.WaitForServiceStatus.assert_called_once_with(native.SERVICE, 1, 360)
            native.start_service(layout)
            native.register_service(layout)
            api.ChangeServiceConfig.assert_called_once()
            api.QueryServiceStatus.side_effect = ServiceError(1060)
            native.stop_service(layout)
            native.register_service(layout)
            api.InstallService.assert_called_once()
            api.RemoveService.side_effect = ServiceError(1060)
            native.remove_service(layout)
            api.QueryServiceStatus.side_effect = ServiceError(5)
            with self.assertRaises(ServiceError):
                native.stop_service(layout)

    def test_destructive_acceptance_refuses_non_ci_and_existing_installations(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'disposable GitHub-hosted'):
                lifecycle._require_disposable_environment()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            layout = SimpleNamespace(system='Linux', runtime=root / 'runtime', state=root / 'state', definition=root / 'service')
            safe_os = SimpleNamespace(name='posix', environ={'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted'},
                                      geteuid=lambda: 0, chown=Mock(), chmod=Mock())
            with patch.object(lifecycle, 'os', safe_os), patch.object(lifecycle, 'native_layout', return_value=layout):
                self.assertIs(lifecycle._require_disposable_environment(), layout)
                layout.runtime.mkdir()
                safe_os.chown.reset_mock()
                with self.assertRaisesRegex(RuntimeError, 'pre-existing installation'):
                    lifecycle._require_disposable_environment()
                safe_os.chown.assert_not_called()

    def test_acceptance_status_and_native_exit_checks_are_specific(self):
        client = SimpleNamespace(call=Mock(return_value={'ok': True, 'service': 'running', 'measurements_enabled': False, 'paired': False}))
        self.assertEqual(lifecycle._fixture_status(client)['service'], 'running')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            layout = SimpleNamespace(system='Windows')
            with patch.object(lifecycle.subprocess, 'run', return_value=SimpleNamespace(returncode=10, stderr=b'')):
                lifecycle._fixture_native(layout, root / 'fixture.exe', root, b'a' * 32, 'uninstall')
            with patch.object(lifecycle.subprocess, 'run', return_value=SimpleNamespace(returncode=20, stderr=b'fixture')):
                with self.assertRaisesRegex(AssertionError, 'helper exit 20'):
                    lifecycle._fixture_native(layout, root / 'fixture.exe', root, b'a' * 32, 'repair')
