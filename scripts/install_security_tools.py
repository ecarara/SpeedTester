#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Install pinned release binaries without executing downloaded installers."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def install(name, destination):
    manifest = json.loads((ROOT / 'security/tools.json').read_text())
    entry = manifest[name]
    asset = entry['archives'][platform.system() + '-' + platform.machine()]
    url = f'https://github.com/{entry["repository"]}/releases/download/v{entry["version"]}/{asset["name"]}'
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read(100 * 1024 * 1024 + 1)
    if hashlib.sha256(data).hexdigest() != asset['sha256']:
        raise ValueError('Security tool checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        member = next(item for item in archive.getmembers()
                      if item.isfile() and (item.name == name or item.name.endswith('/bin/' + name)))
        binary = archive.extractfile(member).read()
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination / (name + '.tmp')
    temporary.write_bytes(binary)
    temporary.chmod(0o755)
    os.replace(temporary, destination / name)
    print(f'{name} {entry["version"]}: checksum verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tools', nargs='+', choices=('grype', 'conftest', 'gh'))
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    for name in args.tools:
        install(name, args.destination)


if __name__ == '__main__':
    main()
