# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Contract for the opt-in speedtester-agent package lifecycle."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AGENT = ROOT / "packaging" / "linux" / "agent"


def load_agent():
    spec = importlib.util.spec_from_file_location(
        "speedtester_agent_package", AGENT / "speedtester-agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.agent = load_agent()
        self.state = self.base / "state"
        self.entry = self.base / "applications" / "speedtester-client.desktop"
        self.runtime = self.base / "opt" / "SpeedTesterClient"
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_text("")
        self.agent.STATE = self.state
        self.agent.BOOTSTRAP = self.state / "service.json"
        self.agent.ENTRY = self.entry
        self.agent.RUNTIME = self.runtime
        self.agent.require_root = lambda: None
        self.calls = []
        self.commands = []

        def run(command, **_options):
            self.commands.append(command)
            return SimpleNamespace(returncode=0, stdout="active")

        self.agent.subprocess = SimpleNamespace(run=run)
        self.agent.invoke = self._invoke

    def _invoke(self, operation, key):
        self.calls.append((operation, key))
        self.state.mkdir(parents=True, exist_ok=True)
        self.agent.BOOTSTRAP.write_text(
            json.dumps(
                {"format": "cararalab-speedtester-desktop-v1", "control_key": key}
            )
        )
        return 0

    def tearDown(self):
        self.temporary.cleanup()

    def test_enable_installs_runtime_entry_and_control_key(self):
        self.assertEqual(self.agent.enable(), 0)
        operation, key = self.calls[0]
        self.assertEqual(operation, "install")
        self.assertEqual(len(key), 64)
        self.assertIn(
            self.runtime,
            [
                Path(line.removeprefix("Exec="))
                for line in self.entry.read_text().splitlines()
                if line.startswith("Exec=")
            ],
        )
        self.assertFalse((self.state / "disabled").exists())

    def test_enable_of_existing_installation_repairs_with_its_key(self):
        key = "a" * 64
        self.state.mkdir(parents=True)
        self.agent.BOOTSTRAP.write_text(
            json.dumps(
                {"format": "cararalab-speedtester-desktop-v1", "control_key": key}
            )
        )
        self.assertEqual(self.agent.enable(), 0)
        self.assertEqual(self.calls, [("repair", key)])

    def test_disable_marks_the_agent_so_upgrades_do_not_reenable_it(self):
        self.state.mkdir(parents=True)
        self.agent.BOOTSTRAP.write_text(
            '{"format": "cararalab-speedtester-desktop-v1"}'
        )
        self.assertEqual(self.agent.disable(), 0)
        self.assertTrue((self.state / "disabled").exists())
        self.assertIn(
            ["systemctl", "disable", "--now", self.agent.SERVICE], self.commands
        )

    def test_disable_before_install_does_not_create_state(self):
        self.assertEqual(self.agent.disable(), 0)
        self.assertFalse(self.state.exists())

    def test_remove_uninstalls_and_deletes_the_menu_entry(self):
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text("[Desktop Entry]")
        self.state.mkdir(parents=True)
        self.agent.BOOTSTRAP.write_text(
            json.dumps(
                {"format": "cararalab-speedtester-desktop-v1", "control_key": "b" * 64}
            )
        )
        self.assertEqual(self.agent.remove(), 0)
        self.assertEqual(self.calls, [("uninstall", "b" * 64)])
        self.assertFalse(self.entry.exists())

    def test_unknown_command_is_rejected_without_side_effects(self):
        with (
            patch.object(sys, "argv", ["speedtester-agent", "activate"]),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(self.agent.main(), 1)
        self.assertEqual(self.calls, [])


class AgentPackagingTests(unittest.TestCase):
    def test_install_scriptlet_repairs_only_an_enabled_existing_agent(self):
        script = (AGENT / "speedtester-agent.install").read_text()
        self.assertIn("/var/lib/cararalab-speedtester-client/service.json", script)
        self.assertIn("/var/lib/cararalab-speedtester-client/disabled", script)
        self.assertIn("não ativa o compartilhamento", script)
        self.assertIn("sudo speedtester-agent enable", script)
        install, upgrade = script.split("post_install()", 1)[1].split(
            "post_upgrade()", 1
        )
        self.assertNotIn("repair", install)
        self.assertIn("speedtester-agent repair", upgrade)
        self.assertNotIn("systemctl", script)

    def test_package_ships_the_frozen_bundle_without_precreating_the_service(self):
        build = (AGENT / "PKGBUILD").read_text()
        self.assertIn("SpeedTesterClient-${pkgver}-linux-x86_64.tar.gz", build)
        self.assertNotIn(".desktop", build)
        self.assertIn("'!strip'", build)
        self.assertNotIn("systemctl", build)
        self.assertNotIn("/opt/", build)


if __name__ == "__main__":
    unittest.main()
