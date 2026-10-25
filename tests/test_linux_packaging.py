# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Static contract tests for the Linux desktop integration."""
from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
LINUX = ROOT / "packaging" / "linux"


class LinuxPackagingTests(TestCase):
    def test_desktop_entry_uses_freedesktop_contract(self):
        desktop = (LINUX / "speedtester.desktop.in").read_text(encoding="utf-8")
        self.assertIn("Type=Application", desktop)
        self.assertIn('Exec="@SPEEDTESTER_LAUNCHER@" open', desktop)
        self.assertIn("Icon=speedtester", desktop)
        self.assertIn("Categories=Network;Utility;", desktop)

    def test_user_services_share_expected_paths_and_contract(self):
        for name in ("speedtester-api.service", "speedtester-client.service"):
            unit = (LINUX / name).read_text(encoding="utf-8")
            self.assertIn("EnvironmentFile=-%h/.config/speedtester/speedtester.env", unit)
            self.assertIn("%h/.local/share/speedtester/venv/bin/python", unit)
            self.assertIn("WantedBy=default.target", unit)
        client = (LINUX / "speedtester-client.service").read_text(encoding="utf-8")
        self.assertIn("Requires=speedtester-api.service", client)
        self.assertIn("-m collector.collector", client)
        self.assertIn("Environment=DB_PATH=%h/.local/share/speedtester/data/speedtester.db", client)
        api = (LINUX / "speedtester-api.service").read_text(encoding="utf-8")
        self.assertIn("Environment=DB_PATH=%h/.local/share/speedtester/data/speedtester.db", api)
        self.assertIn("Environment=SPEEDTESTER_LOCAL_MODE=true", api)

    def test_system_packages_use_frozen_runtime_and_keep_user_install_separate(self):
        for service, name in (("api", "SpeedTesterAPI"), ("client", "SpeedTesterClient")):
            unit = (LINUX / "system" / f"speedtester-{service}.service").read_text()
            self.assertIn(f"ExecStart=/usr/lib/speedtester/runtime/{name}/{name}", unit)
            self.assertNotIn("venv", unit)
            self.assertNotIn("PYTHONPATH", unit)
            self.assertIn("DB_PATH=%h/.local/share/speedtester/data/speedtester.db", unit)
        launcher = (LINUX / "system/speedtester-launcher").read_text()
        self.assertIn("runtime/SpeedTesterLauncher/SpeedTesterLauncher", launcher)
        for name in ("build-deb.sh", "build-rpm.sh"):
            builder = (LINUX / name).read_text()
            self.assertIn("SPEEDTESTER_RUNTIME", builder)
            self.assertIn("build_linux_runtime.py", builder)
            self.assertNotIn('cp -a "$VENV', builder)
        control = (LINUX / "debian/control.in").read_text()
        self.assertIn("libc6 (>= @GLIBC_VERSION@)", control)
        self.assertNotIn("python3", control)
        spec = (LINUX / "rpm/speedtester.spec").read_text()
        self.assertIn("cp -a runtime", spec)
        self.assertNotIn("Requires:       /usr/bin/python", spec)

    def test_installation_has_all_freedesktop_icon_sizes(self):
        for size in (16, 32, 48, 64, 128, 256, 512):
            icon = ROOT / "assets" / "icons" / "hicolor" / str(size) / "apps" / "speedtester.png"
            self.assertTrue(icon.is_file(), icon)

    def test_scripts_preserve_data_by_default(self):
        uninstall = (LINUX / "uninstall-user.sh").read_text(encoding="utf-8")
        self.assertIn('SPEEDTESTER_PURGE_DATA:-0', uninstall)
        self.assertIn("SPEEDTESTER_PURGE_DATA=1", uninstall)

    def test_install_script_exposes_uninstall_option(self):
        installer = (LINUX / "install-user.sh").read_text(encoding="utf-8")
        self.assertIn("uninstall|--uninstall", installer)
        self.assertIn('exec "$SCRIPT_DIR/uninstall-user.sh"', installer)
        self.assertIn("speedtester.env.example", installer)
        self.assertIn("configure-user.sh", installer)

    def test_installation_provisions_user_configuration_for_arch_package(self):
        example = (LINUX / "speedtester.env.example").read_text(encoding="utf-8")
        install = (LINUX / "arch" / "speedtester.install").read_text(encoding="utf-8")
        pkgbuild = (LINUX / "arch" / "PKGBUILD").read_text(encoding="utf-8")
        self.assertIn("IPERF3_SERVER=", example)
        self.assertNotIn("DB_PATH=", example)
        self.assertIn("_speedtester_configure_user", install)
        self.assertIn("configure-user.sh", install)
        self.assertIn("/usr/share/speedtester/speedtester.env.example", install)
        self.assertIn("speedtester.env.example", pkgbuild)
        self.assertTrue((LINUX / "configure-user.sh").is_file())

    def test_package_manifests_have_uninstall_paths(self):
        control = (LINUX / "debian" / "control.in").read_text(encoding="utf-8")
        spec = (LINUX / "rpm" / "speedtester.spec").read_text(encoding="utf-8")
        appimage_install = (LINUX / "appimage" / "install-appimage.sh").read_text(encoding="utf-8")
        appimage_uninstall = LINUX / "appimage" / "uninstall-appimage.sh"
        self.assertIn("Package: speedtester", control)
        self.assertIn("%postun", spec)
        self.assertIn("configure-user.sh", control + spec)
        self.assertIn("speedtester.env.example", spec)
        self.assertIn("configure-user.sh", (LINUX / "debian" / "postinst").read_text(encoding="utf-8"))
        self.assertIn("--uninstall", appimage_install)
        self.assertTrue(appimage_uninstall.is_file())

    def test_flatpak_manifest_and_installation_contract(self):
        flatpak_dir = LINUX / "flatpak"
        manifest = (flatpak_dir / "io.github.ecarara.SpeedTester.yml").read_text(encoding="utf-8")
        installer = (flatpak_dir / "install-flatpak.sh").read_text(encoding="utf-8")
        self.assertIn("id: io.github.ecarara.SpeedTester", manifest)
        self.assertIn("runtime: org.freedesktop.Platform", manifest)
        self.assertIn("--talk-name=org.freedesktop.portal.Desktop", manifest)
        self.assertIn("--uninstall", installer)
        self.assertTrue((flatpak_dir / "uninstall-flatpak.sh").is_file())

    def test_arch_package_has_makepkg_and_removal_contract(self):
        arch_dir = LINUX / "arch"
        pkgbuild = (arch_dir / "PKGBUILD").read_text(encoding="utf-8")
        install = (arch_dir / "speedtester.install").read_text(encoding="utf-8")
        self.assertIn("pkgname=speedtester", pkgbuild)
        self.assertIn("license=('GPL-3.0-or-later')", pkgbuild)
        self.assertIn('SOURCE_SHA256', pkgbuild)
        self.assertIn("package()", pkgbuild)
        self.assertIn("'uvicorn'", pkgbuild)
        self.assertIn("'python>=3.11'", pkgbuild)
        self.assertIn("'python<3.15'", pkgbuild)
        self.assertNotIn("'python-uvicorn'", pkgbuild)
        self.assertIn("post_remove()", install)
        self.assertIn("_speedtester_migrate_legacy_user_units", install)
        self.assertIn("WorkingDirectory=%h/.local/share/speedtester/app", install)
        self.assertTrue((LINUX / "build-pacman.sh").is_file())

    def test_isolated_install_smoke_exists(self):
        smoke = ROOT / "scripts" / "smoke_linux_install.sh"
        self.assertTrue(smoke.is_file())
        self.assertIn("SPEEDTESTER_PURGE_DATA=1", smoke.read_text(encoding="utf-8"))
