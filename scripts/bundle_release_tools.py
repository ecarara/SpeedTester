#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Add the pinned iPerf3 and license/source notices to native release packages."""
import argparse
from pathlib import Path
from bundle_iperf import build
from build_desktop import notices


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('--version', required=True)
    arguments = parser.parse_args()
    notices(arguments.bundle)
    build(arguments.bundle, arguments.version)
