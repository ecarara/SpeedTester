# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Desktop-safe path resolution tests."""
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from shared.settings import load_settings


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
