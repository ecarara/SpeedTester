# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Static contract tests for the Windows MSIX packaging."""
from pathlib import Path
from unittest import TestCase
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "packaging" / "windows"


class WindowsPackagingTests(TestCase):
    def test_msix_manifest_declares_start_menu_visuals(self):
        source = (WINDOWS / "AppxManifest.xml.in").read_text(encoding="utf-8")
        manifest = ET.fromstring(source.replace('@VERSION@', '0.3.0.0').replace('@ARCH@', 'x64'))
        ns = {
            "appx": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
            "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
            "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
        }
        identity = manifest.find("appx:Identity", ns)
        visuals = manifest.find(".//uap:VisualElements", ns)
        self.assertEqual(identity.attrib["Name"], "ecarara.SpeedTester")
        self.assertEqual(visuals.attrib["Square44x44Logo"], "Assets\\Square44x44Logo.png")
        self.assertEqual(visuals.attrib["Square150x150Logo"], "Assets\\Square150x150Logo.png")
        capability = manifest.find("appx:Capabilities/rescap:Capability", ns)
        self.assertIsNotNone(capability)
        self.assertEqual(capability.attrib["Name"], "runFullTrust")

    def test_windows_scripts_have_install_and_uninstall_paths(self):
        install = (WINDOWS / "install-msix.ps1").read_text(encoding="utf-8")
        uninstall = (WINDOWS / "uninstall-msix.ps1").read_text(encoding="utf-8")
        builder = (WINDOWS / "build-msix.ps1").read_text(encoding="utf-8")
        self.assertIn("Add-AppxPackage", install)
        self.assertIn("Register-ScheduledTask", install)
        self.assertIn("Remove-AppxPackage", uninstall)
        self.assertIn("Unregister-ScheduledTask", uninstall)
        self.assertIn("MakeAppx.exe", builder)

    def test_msix_assets_have_required_base_sizes(self):
        assets = ROOT / "assets" / "packaging" / "windows" / "msix"
        for name in ("Square44x44Logo.png", "Square150x150Logo.png", "StoreLogo.png"):
            self.assertTrue((assets / name).is_file(), name)
