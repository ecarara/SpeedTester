# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Static contract tests for the macOS application bundle."""
from pathlib import Path
from unittest import TestCase
import plistlib


ROOT = Path(__file__).resolve().parents[1]
MACOS = ROOT / "packaging" / "macos"


class MacOSPackagingTests(TestCase):
    def test_bundle_info_plist_declares_application_identity(self):
        source = (MACOS / "Info.plist.in").read_bytes()
        plist = plistlib.loads(source.replace(b"@VERSION@", b"0.3.0").replace(b"@BUILD_VERSION@", b"030"))
        self.assertEqual(plist["CFBundleIdentifier"], "io.github.ecarara.SpeedTester")
        self.assertEqual(plist["CFBundleExecutable"], "SpeedTesterLauncher")
        self.assertEqual(plist["CFBundleIconFile"], "SpeedTester.icns")

    def test_launch_agent_matches_desktop_service_contract(self):
        source = (MACOS / "LaunchAgents" / "speedtester-client.service.plist.in").read_bytes()
        plist = plistlib.loads(source.replace(b"@CLIENT_PATH@", b"/Applications/SpeedTester.app/Contents/MacOS/SpeedTesterClient"))
        self.assertEqual(plist["Label"], "speedtester-client.service")
        self.assertTrue(plist["RunAtLoad"])
        self.assertTrue(plist["KeepAlive"])

    def test_build_install_and_uninstall_paths_exist(self):
        self.assertTrue((MACOS / "build-app.sh").is_file())
        install = (MACOS / "install-dmg.sh").read_text(encoding="utf-8")
        uninstall = (MACOS / "uninstall-app.sh").read_text(encoding="utf-8")
        self.assertIn("launchctl bootstrap", install)
        self.assertIn("ditto", install)
        self.assertIn("SPEEDTESTER_SKIP_LAUNCHCTL", install)
        builder = (MACOS / "build-app.sh").read_text(encoding="utf-8")
        self.assertIn("Install SpeedTester.command", builder)
        self.assertIn("Uninstall SpeedTester.command", builder)
        self.assertIn("launchctl bootout", uninstall)
        self.assertIn("SPEEDTESTER_SKIP_LAUNCHCTL", uninstall)
        self.assertIn("--purge-data", uninstall)

    def test_mac_icon_exists(self):
        self.assertTrue((ROOT / "assets" / "packaging" / "macos" / "SpeedTester.icns").is_file())
