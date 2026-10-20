# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Runtime application version shared by the API and dashboard."""

from __future__ import annotations

import os
import re

_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")


def runtime_version() -> str:
    """Return the build-injected version, or dev for local source runs."""
    value = os.environ.get("APP_VERSION", "").strip()
    return value if _VERSION_RE.fullmatch(value) else "dev"


APP_VERSION = runtime_version()
