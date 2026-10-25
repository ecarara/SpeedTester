# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Diagnostics and child-process environment for the native application entries."""
import json
import os
import platform
import sys


def print_runtime_info():
    from shared.version import APP_VERSION
    print(json.dumps({"python": platform.python_version(),
                      "implementation": platform.python_implementation(),
                      "app_version": APP_VERSION,
                      "frozen": bool(getattr(sys, "frozen", False))}))


def prepare_system_children():
    """External Linux tools must load system libraries, not our bundled copies.

    The ELF loader has already initialized this process's library search path.
    Restoring the environment here affects future execs (iperf3, ping, ip,
    systemctl and the browser), while Python continues using its frozen runtime.
    These entries never launch another bundled application as a child.
    """
    if sys.platform == "linux" and getattr(sys, "frozen", False):
        original = os.environ.pop("LD_LIBRARY_PATH_ORIG", None)
        if original:
            os.environ["LD_LIBRARY_PATH"] = original
        else:
            os.environ.pop("LD_LIBRARY_PATH", None)

