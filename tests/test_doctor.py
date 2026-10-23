# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise installation preflight failures without changing the host."""
import importlib.util
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('doctor', ROOT / 'scripts/doctor.py')
doctor = importlib.util.module_from_spec(spec);spec.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def run_doctor(self, arguments, environment=None):
        with patch.object(sys,'argv',['doctor.py',*arguments]), \
             patch.dict(os.environ,environment or {},clear=True), \
             patch('sys.stdout',new_callable=StringIO), patch('sys.stderr',new_callable=StringIO):
            return doctor.main()

    def test_host_preflight_and_tcp_probe_succeed_without_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            env=Path(directory)/'.env';env.write_text('# example\nIPERF3_SERVER=iperf3.example.com\nAPI_PORT=8000\n')
            with patch.object(doctor.subprocess,'run',return_value=MagicMock(returncode=0)) as process, \
                 patch.object(doctor.socket,'create_connection',return_value=MagicMock()) as network:
                self.assertEqual(self.run_doctor(['--env-file',str(env),'--network']),0)
                self.assertEqual(process.call_count,2)
                network.assert_called_once_with(('iperf3.example.com',5201),timeout=5)

    def test_unavailable_docker_and_unreachable_endpoint_fail_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            env=Path(directory)/'.env';env.write_text('IPERF3_SERVER=iperf3.example.com\n')
            with patch.object(doctor.subprocess,'run',side_effect=OSError('missing')), \
                 patch.object(doctor.socket,'create_connection',side_effect=OSError('unreachable')):
                self.assertEqual(self.run_doctor(['--env-file',str(env),'--network']),1)

    def test_missing_environment_and_invalid_configuration_fail_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            env=Path(directory)/'.env'
            self.assertEqual(self.run_doctor(['--env-file',str(env)]),1)
            for contents in ('not an assignment','API_PORT=70000','MEASUREMENTS_PER_QUADRANT=50'):
                env.write_text(contents)
                self.assertEqual(self.run_doctor(['--env-file',str(env)]),1)

    def test_container_rejects_missing_server_and_unavailable_ookla(self):
        with patch.object(doctor.shutil,'which',return_value=None):
            self.assertEqual(self.run_doctor(['--container']),1)
            self.assertEqual(self.run_doctor(['--container'],{'SPEEDTEST_RUNNER':'ookla'}),1)
            self.assertEqual(self.run_doctor(['--container'],{'SPEEDTEST_RUNNER':'fast'}),0)

    def test_automatic_selection_does_not_require_a_manual_server_or_probe_on_install(self):
        with patch.object(doctor.shutil,'which',return_value='/usr/bin/iperf3'), \
                patch.object(doctor.socket,'create_connection') as probe:
            self.assertEqual(self.run_doctor(['--container']),0)
            probe.assert_not_called()

    def test_environment_is_literal_and_does_not_execute_shell(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{},clear=True):
            env=Path(directory)/'.env';marker=Path(directory)/'must-not-exist'
            value='$(touch '+str(marker)+')'
            env.write_text('EXAMPLE="'+value+'"\n')
            doctor.load_env(env)
            self.assertEqual(os.environ['EXAMPLE'],value)
            self.assertFalse(marker.exists())
