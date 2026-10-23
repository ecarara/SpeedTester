# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Locate the measurement tool in a native package or the system installation."""
from pathlib import Path
import shutil
import sys


def iperf_binary():
    name = 'iperf3.exe' if sys.platform == 'win32' else 'iperf3'
    if getattr(sys, 'frozen', False):
        packaged = Path(sys.executable).parent / 'tools' / name
        if packaged.is_file():
            return str(packaged)
    return shutil.which(name) or name
