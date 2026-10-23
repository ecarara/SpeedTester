#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Stamp the package version into a staged runtime before packaging/freezing."""
import argparse
from pathlib import Path
import re


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('app', type=Path)
    parser.add_argument('version')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', args.version):
        parser.error('semantic package version required')
    (args.app / 'shared/_build_version.py').write_text(
        '# SPDX-License-Identifier: GPL-3.0-or-later\n'
        '# Copyright (C) 2026 Edson Angelo Carara\n'
        f'VERSION = {args.version!r}\n', encoding='utf-8')
