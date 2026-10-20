# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Resolve and load the per-user desktop configuration on every OS."""
from __future__ import annotations

import os
import platform
from pathlib import Path
import re


_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def config_path() -> Path:
    """Return the native per-user configuration path."""
    override = os.environ.get("SPEEDTESTER_CONFIG_FILE")
    if override:
        return Path(override).expanduser()

    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "SpeedTester" / "speedtester.env"
    if system == "Windows":
        app_data = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(app_data) / "SpeedTester" / "speedtester.env"
    config_home = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(config_home) / "speedtester" / "speedtester.env"


def _value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_user_environment() -> Path:
    """Load simple KEY=VALUE settings without overriding process variables.

    Package service managers may already inject the environment. Explicit
    process values therefore win over the persisted desktop configuration.
    """
    path = config_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return path

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, raw_value = stripped.partition("=")
        key = key.strip()
        if separator and _KEY.fullmatch(key) and key not in os.environ:
            os.environ[key] = _value(raw_value)
    return path
