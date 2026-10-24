# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Run the actual POSIX/PowerShell configuration flows in isolated user homes."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from shared.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "packaging/linux/speedtester.env.example"


class InstallerFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "speedtester.env"
        self.environment = dict(os.environ, SPEEDTESTER_CONFIG_DIR=str(self.root),
                                SPEEDTESTER_ENV_FILE=str(self.config),
                                SPEEDTESTER_ENV_TEMPLATE=str(TEMPLATE),
                                SPEEDTESTER_NONINTERACTIVE="1", SPEEDTESTER_CONFIRM_EXISTING="1")
        for name in ("SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS", "SPEEDTESTER_CONTRACTED_UPLOAD_MBPS"):
            self.environment.pop(name, None)

    def settings(self):
        with patch.dict(os.environ, {"SPEEDTESTER_CONFIG_FILE": str(self.config),
                                    "HOME": str(self.root), "USERPROFILE": str(self.root)}, clear=True):
            return load_settings()

    def assert_contract(self, download, upload):
        settings = self.settings()
        self.assertEqual((settings.bandwidth_contracted_mbps, settings.bandwidth_contracted_upload_mbps),
                         (download, upload))
        text = self.config.read_text()
        for key in ("BANDWIDTH_CONTRACTED_MBP=", "BANDWIDTH_CONTRACTED_UPLOAD_MBPS="):
            self.assertEqual(sum(line.startswith(key) for line in text.splitlines()), 1)


@unittest.skipIf(os.name == "nt", "POSIX configurator")
class PosixContractInstallerTests(InstallerFixture):
    def run_configure(self, **overrides):
        return subprocess.run(["bash", str(ROOT / "packaging/linux/configure-user.sh")],
                              env=dict(self.environment, **overrides), capture_output=True, text=True, timeout=10)

    def dialogue(self, answers):
        import pty
        import signal
        pid, master = pty.fork()
        if pid == 0:
            os.execve("/bin/bash", ["bash", str(ROOT / "packaging/linux/configure-user.sh")],
                      dict(self.environment, SPEEDTESTER_NONINTERACTIVE="0"))
        output = b""
        completed = False
        try:
            deadline = time.monotonic() + 15
            for prompt, answer in answers:
                while prompt.encode() not in output:
                    if time.monotonic() > deadline:
                        self.fail("installer prompt timeout: " + prompt)
                    if select.select([master], [], [], 0.1)[0]:
                        output += os.read(master, 8192)
                output = output.split(prompt.encode(), 1)[1]
                os.write(master, (answer + "\n").encode())
            while not completed:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited:
                    completed = True
                    self.assertEqual(os.waitstatus_to_exitcode(status), 0)
                elif time.monotonic() > deadline:
                    self.fail("installer completion timeout")
                else:
                    if select.select([master], [], [], 0.1)[0]:
                        try:
                            output += os.read(master, 8192)
                        except OSError:
                            pass
        finally:
            os.close(master)
            if not completed:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)

    def test_noninteractive_values_are_persisted_and_loaded(self):
        result = self.run_configure(SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS="1000",
                                    SPEEDTESTER_CONTRACTED_UPLOAD_MBPS="500")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_contract(1000, 500)
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)

    def test_upgrade_keeps_contract_and_other_configuration(self):
        self.config.write_text("TZ=UTC\nIPERF3_SERVER=manual.example\nIPERF3_PORT=5300\n"
                               "BANDWIDTH_CONTRACTED_MBP=1000\nBANDWIDTH_CONTRACTED_UPLOAD_MBPS=500\n"
                               "API_ADMIN_TOKEN=synthetic-preserved\n")
        self.assertEqual(self.run_configure().returncode, 0)
        self.assert_contract(1000, 500)
        self.assertIn("API_ADMIN_TOKEN=synthetic-preserved", self.config.read_text())
        self.assertIn("IPERF3_SERVER=manual.example", self.config.read_text())
        self.assertEqual(self.settings().timezone, "UTC")

    def test_interactive_new_install_asks_both_speeds_even_if_other_parameters_accepted(self):
        self.dialogue([("Confirmar esses parâmetros?", ""), ("Download contratado", "1000"),
                       ("Upload contratado", "500")])
        self.assert_contract(1000, 500)

    def test_upgrade_migrates_legacy_download_and_asks_missing_upload(self):
        self.config.write_text("TZ=UTC\nIPERF3_SERVER=\nIPERF3_PORT=5201\nBANDWIDTH_CONTRACTED_MBP=1000\n")
        self.dialogue([("Confirmar esses parâmetros?", ""), ("Download contratado", ""),
                       ("Upload contratado", "500")])
        self.assert_contract(1000, 500)
        self.assertEqual(self.settings().timezone, "UTC")

    def test_interactive_upgrade_can_keep_or_edit_existing_values(self):
        self.assertEqual(self.run_configure(SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS="1000",
                                           SPEEDTESTER_CONTRACTED_UPLOAD_MBPS="500").returncode, 0)
        self.dialogue([("Confirmar esses parâmetros?", ""), ("Download contratado", ""),
                       ("Upload contratado", "")])
        self.assert_contract(1000, 500)
        self.dialogue([("Confirmar esses parâmetros?", ""), ("Download contratado", "2000"),
                       ("Upload contratado", "1000")])
        self.assert_contract(2000, 1000)

    def test_invalid_input_is_reprompted_and_decimal_comma_is_normalized(self):
        self.dialogue([("Confirmar esses parâmetros?", ""), ("Download contratado", "0"),
                       ("Download contratado", "nan"), ("Download contratado", "1000,5"),
                       ("Upload contratado", "-1"), ("Upload contratado", "500,25")])
        self.assert_contract(1000.5, 500.25)

    def test_invalid_unattended_values_do_not_change_existing_configuration(self):
        self.config.write_text("TZ=UTC\nBANDWIDTH_CONTRACTED_MBP=1000\n")
        previous = self.config.read_bytes()
        for invalid in ("0", "-1", "nan", "inf", "1e309", "9" * 400, "1\nTZ=bad"):
            with self.subTest(invalid=invalid[:10]):
                result = self.run_configure(SPEEDTESTER_CONTRACTED_UPLOAD_MBPS=invalid)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.config.read_bytes(), previous)

    def test_unattended_unknown_contract_is_not_invented_or_silently_enabled(self):
        result = self.run_configure()
        self.assertEqual(result.returncode, 0)
        self.assert_contract(None, None)
        self.assertIn("AVISO", result.stderr)


POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@unittest.skipUnless(POWERSHELL, "PowerShell runtime required")
class WindowsContractInstallerTests(InstallerFixture):
    def install(self, answers=None, **overrides):
        package = self.root / "package"
        package.mkdir(exist_ok=True)
        (package / "speedtester.env.example").write_text(TEMPLATE.read_text())
        archive = self.root / "synthetic.msix"
        archive.touch()
        self.config = self.root / "appdata/SpeedTester/speedtester.env"
        environment = dict(self.environment, APPDATA=str(self.root / "appdata"),
                           SPEEDTESTER_TEST_PACKAGE=str(package), SPEEDTESTER_TEST_ARCHIVE=str(archive),
                           SPEEDTESTER_TEST_INSTALLER=str(ROOT / "packaging/windows/install-msix.ps1"),
                           SPEEDTESTER_TEST_ANSWERS=json.dumps(answers or []),
                           SPEEDTESTER_NONINTERACTIVE="0" if answers is not None else "1")
        environment.update(overrides)
        command = r'''
$ErrorActionPreference = 'Stop'
$script:answers = [System.Collections.Generic.Queue[string]]::new()
foreach ($answer in (ConvertFrom-Json $env:SPEEDTESTER_TEST_ANSWERS)) { $script:answers.Enqueue($answer) }
function Add-AppxPackage { param($Path) }
function Get-AppxPackage { param($Name, $ErrorAction) [pscustomobject]@{InstallLocation=$env:SPEEDTESTER_TEST_PACKAGE} }
function tzutil.exe { 'UTC' }
function Read-Host {
    param($Prompt)
    Write-Host "PROMPT: $Prompt"
    if ($script:answers.Count -eq 0) { throw 'unexpected prompt' }
    return $script:answers.Dequeue()
}
. $env:SPEEDTESTER_TEST_INSTALLER -PackagePath $env:SPEEDTESTER_TEST_ARCHIVE
'''
        return subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command],
                              env=environment, capture_output=True, text=True, timeout=20)

    def test_real_windows_script_install_then_upgrade_keeps_or_edits_contract(self):
        for answers, expected in ((["", "1000", "500"], (1000, 500)),
                                  (["", "", ""], (1000, 500)),
                                  (["", "2000", "1000"], (2000, 1000))):
            result = self.install(answers)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PROMPT: Download contratado", result.stdout)
            self.assertIn("PROMPT: Upload contratado", result.stdout)
            self.assert_contract(*expected)

    def test_windows_legacy_config_adds_upload_without_losing_other_settings(self):
        result = self.install(SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS="1000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.config.write_text("TZ=UTC\nIPERF3_SERVER=manual.example\nIPERF3_PORT=5300\n"
                               "BANDWIDTH_CONTRACTED_MBP=1000\nAPI_ADMIN_TOKEN=synthetic-preserved\n")
        result = self.install(["", "", "500"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_contract(1000, 500)
        self.assertIn("API_ADMIN_TOKEN=synthetic-preserved", self.config.read_text())
        self.assertEqual(self.settings().iperf3_server, "manual.example")

    def test_windows_invalid_values_reprompt_without_accepting_nan_or_zero(self):
        result = self.install(["", "0", "nan", "1000,5", "Infinity", "500,25"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_contract(1000.5, 500.25)

    def test_windows_unattended_invalid_value_never_rewrites_existing_config(self):
        self.assertEqual(self.install(SPEEDTESTER_CONTRACTED_DOWNLOAD_MBPS="1000",
                                     SPEEDTESTER_CONTRACTED_UPLOAD_MBPS="500").returncode, 0)
        before = self.config.read_bytes()
        for invalid in ("0", "-1", "nan", "Infinity", "1e309", "9" * 400, "1\nTZ=bad"):
            result = self.install(SPEEDTESTER_CONTRACTED_UPLOAD_MBPS=invalid)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.config.read_bytes(), before)
