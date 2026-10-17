# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Prefer the packaged, manifest-covered tool over workstation executables."""
from pathlib import Path
import shutil
import sys


def iperf_binary():
    name = "iperf3.exe" if sys.platform == "win32" else "iperf3"
    if getattr(sys, "frozen", False):
        candidate = Path(sys.executable).parent / "tools" / name
        return str(candidate) if candidate.is_file() and not candidate.is_symlink() else None
    return shutil.which(name)
