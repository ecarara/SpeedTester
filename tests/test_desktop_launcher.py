# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Contract tests for the cross-platform desktop launcher."""
import os
from unittest import TestCase
from unittest.mock import patch

from desktop_launcher import (
    LauncherConfig,
    LauncherError,
    ServiceController,
    main,
    open_dashboard,
    validate_dashboard_url,
)


class DesktopLauncherTests(TestCase):
    def test_default_configuration_is_local_and_user_scoped(self):
        with patch.dict(os.environ, {}, clear=True):
            config = LauncherConfig.from_environment()
        self.assertEqual(config.dashboard_url, "http://127.0.0.1:8000/")
        self.assertEqual(config.service_name, "speedtester-client.service")
        self.assertEqual(config.api_service_name, "speedtester-api.service")

    def test_environment_can_select_remote_dashboard_without_credentials(self):
        with patch.dict(os.environ, {
            "SPEEDTESTER_DASHBOARD_URL": "https://speedtester.example.test/",
            "SPEEDTESTER_SERVICE_NAME": "custom-speedtester.service",
        }, clear=True):
            config = LauncherConfig.from_environment()
        self.assertEqual(config.dashboard_url, "https://speedtester.example.test/")
        self.assertEqual(config.service_name, "custom-speedtester.service")

    def test_dashboard_url_rejects_credentials_and_non_http_schemes(self):
        for value in ("file:///tmp/dashboard", "https://user:pass@example.test/"):
            with self.assertRaises(LauncherError):
                validate_dashboard_url(value)

    def test_linux_service_commands_are_fixed_argument_lists(self):
        controller = ServiceController("speedtester-client.service", "Linux")
        with patch("desktop_launcher._run") as run:
            run.return_value.returncode = 0
            self.assertEqual(controller.execute("status"), "active")
            run.assert_called_once_with(["systemctl", "--user", "status", "speedtester-client.service"])

    def test_windows_service_commands_use_task_scheduler(self):
        controller = ServiceController("SpeedTester", "Windows")
        with patch("desktop_launcher._run") as run:
            run.return_value.returncode = 0
            self.assertEqual(controller.execute("start"), "started")
            run.assert_called_once_with(["schtasks", "/Run", "/TN", "SpeedTester"])

    def test_macos_service_commands_use_current_user_launchd_domain(self):
        controller = ServiceController("com.ecarara.speedtester", "Darwin")
        with patch("desktop_launcher._run") as run, patch("desktop_launcher.os.getuid", return_value=501):
            run.return_value.returncode = 0
            self.assertEqual(controller.execute("status"), "active")
            run.assert_called_once_with(["launchctl", "print", "gui/501/com.ecarara.speedtester"])

    def test_open_action_only_opens_the_validated_dashboard(self):
        config = LauncherConfig("https://speedtester.example.test/")
        with patch("desktop_launcher.webbrowser.open", return_value=True) as open_browser:
            open_dashboard(config)
        open_browser.assert_called_once_with("https://speedtester.example.test/", new=2)

    def test_local_open_starts_api_and_waits_for_health(self):
        config = LauncherConfig("http://127.0.0.1:8000/")
        with (
            patch("desktop_launcher._dashboard_is_ready", side_effect=(False, True)),
            patch("desktop_launcher.ServiceController") as controller_type,
            patch("desktop_launcher.webbrowser.open", return_value=True) as open_browser,
        ):
            open_dashboard(config)
        controller_type.assert_called_once_with("speedtester-api.service")
        controller_type.return_value.execute.assert_called_once_with("start")
        open_browser.assert_called_once_with("http://127.0.0.1:8000/", new=2)

    def test_local_open_reuses_an_already_healthy_api(self):
        config = LauncherConfig("http://127.0.0.1:8000/")
        with (
            patch("desktop_launcher._dashboard_is_ready", return_value=True),
            patch("desktop_launcher.ServiceController") as controller_type,
            patch("desktop_launcher.webbrowser.open", return_value=True) as open_browser,
        ):
            open_dashboard(config)
        controller_type.assert_not_called()
        open_browser.assert_called_once_with("http://127.0.0.1:8000/", new=2)

    def test_local_open_does_not_use_an_unrelated_process_on_dashboard_port(self):
        config = LauncherConfig("http://127.0.0.1:8000/")
        with (
            patch("desktop_launcher.platform.system", return_value="Darwin"),
            patch("desktop_launcher._dashboard_is_ready", return_value=False),
            patch("desktop_launcher._local_endpoint_is_bound", return_value=True),
            patch("desktop_launcher.ServiceController") as controller_type,
            patch("desktop_launcher.webbrowser.open") as open_browser,
        ):
            with self.assertRaisesRegex(LauncherError, "porta.*ocupada"):
                open_dashboard(config)
        controller_type.assert_not_called()
        open_browser.assert_not_called()

    def test_linux_local_open_moves_to_free_port_when_default_is_occupied(self):
        config = LauncherConfig("http://127.0.0.1:8000/")
        with (
            patch("desktop_launcher.platform.system", return_value="Linux"),
            patch("desktop_launcher._dashboard_is_ready", side_effect=(False, True)),
            patch("desktop_launcher._local_endpoint_is_bound", return_value=True),
            patch("desktop_launcher._find_free_local_port", return_value=8001),
            patch("desktop_launcher._persist_local_port") as persist_port,
            patch("desktop_launcher._reload_user_manager"),
            patch("desktop_launcher.ServiceController") as controller_type,
            patch("desktop_launcher.webbrowser.open", return_value=True) as open_browser,
        ):
            open_dashboard(config)
        persist_port.assert_called_once_with(8001)
        controller_type.return_value.execute.assert_called_once_with("start")
        open_browser.assert_called_once_with("http://127.0.0.1:8001/", new=2)

    def test_main_open_reports_success(self):
        with patch("desktop_launcher.open_dashboard") as open_action:
            self.assertEqual(main(["open", "--url", "https://speedtester.example.test/"]), 0)
        open_action.assert_called_once()

    def test_main_restart_stops_and_starts_the_configured_service(self):
        with patch("desktop_launcher.ServiceController") as controller_type:
            self.assertEqual(main(["restart", "--service", "SpeedTester"]), 0)
        controller = controller_type.return_value
        controller.execute.assert_any_call("stop")
        controller.execute.assert_any_call("start")
