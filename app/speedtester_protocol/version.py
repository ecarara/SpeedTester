# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Public build identity. Diagnostics intentionally omit account/host secrets."""

import platform
import re

CLIENT_VERSION = "0.3.0.dev20"
BUILD_REVISION = "source"
RELEASE_VERSION = "0.4.54"


def set_build_revision(value):
    global BUILD_REVISION
    if value != "source" and not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("invalid_build_revision")
    BUILD_REVISION = value


def build_label():
    return RELEASE_VERSION + " · " + CLIENT_VERSION


def diagnostic_text(service=None):
    lines = [
        "SpeedTester Client " + RELEASE_VERSION,
        "Protocol: " + CLIENT_VERSION,
        "Build: " + BUILD_REVISION,
        "Platform: " + platform.system() + " / " + platform.machine(),
    ]
    if service:
        lines.extend(
            [
                "Service release: " + str(service.get("release_version", "unknown")),
                "Service protocol: " + str(service.get("client_version", "unknown")),
                "Service build: " + str(service.get("build_revision", "unknown")),
            ]
        )
    return "\n".join(lines)
