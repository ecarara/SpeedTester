# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Execute interpreter probes and the source installer without downloads/services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('python_bootstrap', ROOT / 'install-speedtester-client.py')
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


@unittest.skipIf(os.name == 'nt', 'POSIX source installer')
class InterpreterSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.jsonl'
        self.environment = dict(os.environ, HOME=str(self.root / 'home'),
                                XDG_DATA_HOME=str(self.root / 'data'),
                                XDG_CONFIG_HOME=str(self.root / 'config'),
                                SPEEDTESTER_SOURCE_DIR=str(ROOT), SPEEDTESTER_SKIP_SYSTEMD='1',
                                SPEEDTESTER_NONINTERACTIVE='1', APP_VERSION='0.4.99')
        for name in ('SPEEDTESTER_PYTHON', 'SPEEDTESTER_INSTALL_ROOT', 'SPEEDTESTER_ENV_FILE',
                     'SPEEDTESTER_CONFIG_DIR', 'SPEEDTESTER_ENV_TEMPLATE'):
            self.environment.pop(name, None)
        # Use only our interpreter fixtures; retain real file/configuration tools.
        for name in ('bash', 'dirname', 'mkdir', 'rm', 'cp', 'install', 'sed', 'chmod',
                     'date', 'readlink', 'cat', 'grep', 'mv', 'mktemp', 'head', 'tr', 'awk'):
            executable = shutil.which(name)
            if executable:
                (self.bin / name).symlink_to(executable)
        self.environment['PATH'] = str(self.bin)
        for name in ('iperf3', 'systemctl'):
            executable = self.bin / name
            executable.write_text('#!/bin/sh\nexit 0\n')
            executable.chmod(0o755)

    def python(self, name, minor, *, implementation='cpython', broken=False):
        executable = self.bin / name
        executable.write_text(f'''#!{sys.executable}
import json, pathlib, subprocess, sys, venv
with open({str(self.log)!r}, 'a') as log:
    log.write(json.dumps([pathlib.Path(sys.argv[0]).name, sys.argv[1:]]) + '\\n')
if sys.argv[1] == '-c':
    if {broken!r}:
        raise SystemExit(1)
    sys.version_info = (3, {minor}, 0)
    sys.implementation.name = {implementation!r}
    exec(sys.argv[2])
elif sys.argv[1:3] == ['-m', 'venv']:
    target = pathlib.Path(sys.argv[-1]) / 'bin/python'
    if '--clear' in sys.argv and target.parent.parent.exists():
        import shutil
        shutil.rmtree(target.parent.parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('#!/bin/sh\\nexit 0\\n')
    target.chmod(0o755)
else:
    raise SystemExit(subprocess.call([{sys.executable!r}] + sys.argv[1:]))
''')
        executable.chmod(0o755)
        return str(executable)

    def select(self):
        with patch.dict(os.environ, self.environment, clear=True):
            return installer.select_python()

    def install(self, **overrides):
        return subprocess.run(['/bin/bash', str(ROOT / 'packaging/linux/install-user.sh')],
                              env=dict(self.environment, **overrides), capture_output=True,
                              text=True, timeout=30)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_default_315_selects_314_and_shell_uses_it_for_stamp_and_venv(self):
        self.python('python3', 15)
        expected = self.python('python3.14', 14)
        self.assertEqual(self.select(), expected)
        # Keep the real requirement check, subprocess probes, and shell install.
        # Only host prerequisites and the release download are synthetic.
        with patch.dict(os.environ, self.environment, clear=True), \
                patch.object(installer.platform, 'system', return_value='Linux'), \
                patch.object(installer.platform, 'machine', return_value='x86_64'), \
                patch.object(installer.os, 'geteuid', return_value=1000), \
                patch.object(installer.sys.stdin, 'isatty', return_value=True), \
                patch.object(installer, 'latest_release', return_value=('0.4.99',)), \
                patch.object(installer, 'download_archive', return_value='0.4.99'), \
                patch.object(installer, 'extract_archive', return_value=ROOT):
            self.assertEqual(installer.check_requirements(), expected)
            self.assertEqual(installer.install(), 0)
        calls = self.calls()
        self.assertTrue(any(name == 'python3.14' and args[0].endswith('stamp_version.py')
                            for name, args in calls))
        self.assertTrue(any(name == 'python3.14' and args[:2] == ['-m', 'venv']
                            for name, args in calls))
        self.assertFalse(any(name == 'python3' for name, _ in calls))
        self.assertTrue((self.root / 'data/applications/speedtester.desktop').is_file())

    def test_shell_also_selects_314_without_bootstrap_override(self):
        self.python('python3', 15)
        self.python('python3.14', 14)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(name == 'python3.14' for name, _ in self.calls()))

    def test_311_through_313_remain_selectable_including_unversioned_python(self):
        for minor in (11, 12, 13):
            for name in (f'python3.{minor}', 'python3'):
                with self.subTest(minor=minor, name=name):
                    expected = self.python(name, minor)
                    self.assertEqual(self.select(), expected)
                    Path(expected).unlink()

    def test_invalid_or_missing_venv_candidates_are_skipped(self):
        self.python('python3.14', 14, broken=True)
        self.python('python3.13', 13, implementation='pypy')
        expected = self.python('python3.12', 12)
        self.assertEqual(self.select(), expected)

    def test_unsupported_interpreters_fail_before_download_or_install_mutations(self):
        # Validation must still run when Python assertions are disabled.
        self.environment['PYTHONOPTIMIZE'] = '1'
        for minor in (10, 15):
            with self.subTest(minor=minor):
                self.python('python3', minor)
                with self.assertRaises(installer.InstallationError):
                    self.select()
                with patch.dict(os.environ, self.environment, clear=True), \
                        patch.object(installer.platform, 'system', return_value='Linux'), \
                        patch.object(installer.platform, 'machine', return_value='x86_64'), \
                        patch.object(installer.os, 'geteuid', return_value=1000), \
                        patch.object(installer.sys.stdin, 'isatty', return_value=True), \
                        patch.object(installer, 'latest_release') as download:
                    with self.assertRaises(installer.InstallationError):
                        installer.install()
                    download.assert_not_called()
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('3.15', result.stderr)
                self.assertFalse((self.root / 'data').exists())

    def test_explicit_invalid_selection_never_falls_back_or_touches_existing_install(self):
        expected = self.python('python3.14', 14)
        bad = self.python('python3', 15)
        target = self.root / 'data/speedtester/app'
        target.mkdir(parents=True)
        sentinel = target / 'keep'
        sentinel.write_text('working installation')
        for override in (bad, str(self.bin / 'missing')):
            with self.subTest(override=override):
                self.environment['SPEEDTESTER_PYTHON'] = override
                with self.assertRaises(installer.InstallationError):
                    self.select()
                result = self.install()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sentinel.read_text(), 'working installation')
        self.assertFalse(any(name == Path(expected).name for name, _ in self.calls()))

    def test_probe_execution_failure_is_reported_as_validation_failure(self):
        self.python('python3.14', 14)
        for error in (OSError('cannot execute'), subprocess.TimeoutExpired('python', 10)):
            with self.subTest(error=type(error).__name__), patch.object(installer.subprocess, 'run', side_effect=error):
                with self.assertRaises(installer.InstallationError):
                    self.select()

    def test_reinstall_refreshes_venv_but_preserves_configuration_and_history(self):
        self.python('python3.14', 14)
        self.assertEqual(self.install().returncode, 0)
        old_venv = self.root / 'data/speedtester/venv/old-minor-sentinel'
        old_venv.touch()
        config = self.root / 'config/speedtester/speedtester.env'
        with config.open('a') as stream:
            stream.write('\n# preserve config\n')
        history = self.root / 'data/speedtester/data/history-sentinel'
        history.write_text('history')
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(old_venv.exists())
        self.assertIn('# preserve config', config.read_text())
        self.assertEqual(history.read_text(), 'history')

if __name__ == '__main__':
    unittest.main()
