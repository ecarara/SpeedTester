# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Desktop-safe path resolution tests."""
from pathlib import Path
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from shared.settings import load_settings
from shared.user_config import config_path, load_user_environment


class SettingsPathTests(TestCase):
    def test_systemd_home_specifier_is_resolved_in_environment_file_values(self):
        with patch.dict(
            "os.environ",
            {"DB_PATH": "%h/.local/share/speedtester/data/speedtester.db"},
            clear=False,
        ):
            settings = load_settings()
        self.assertEqual(
            settings.db_path,
            str(Path.home() / ".local/share/speedtester/data/speedtester.db"),
        )

    def test_desktop_default_database_is_user_writable(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = load_settings()
        self.assertEqual(
            settings.db_path,
            str(Path.home() / ".local/share/speedtester/data/speedtester.db"),
        )

    def test_local_mode_disables_dashboard_login_without_changing_server_default(self):
        with patch.dict(
            "os.environ",
            {"SPEEDTESTER_LOCAL_MODE": "true", "API_REQUIRE_LOGIN": "true"},
            clear=False,
        ):
            settings = load_settings()
        self.assertFalse(settings.api_require_login)

        with patch.dict(
            "os.environ",
            {"SPEEDTESTER_LOCAL_MODE": "false", "API_REQUIRE_LOGIN": "true"},
            clear=False,
        ):
            settings = load_settings()
        self.assertTrue(settings.api_require_login)

    def test_persisted_desktop_configuration_is_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "speedtester.env"
            config.write_text(
                "# user config\nIPERF3_SERVER=iperf.example\nTZ=America/Sao_Paulo\n",
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"SPEEDTESTER_CONFIG_FILE": str(config)}, clear=True):
                self.assertEqual(config_path(), config)
                load_user_environment()
                self.assertEqual(os.environ["IPERF3_SERVER"], "iperf.example")
                self.assertEqual(os.environ["TZ"], "America/Sao_Paulo")
