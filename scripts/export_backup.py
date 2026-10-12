#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Copy only the last successful immutable snapshot to a private sync folder."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

NAME = re.compile(r'speedtester-\d{8}T\d{6}Z-\d+[.]db')


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def export(source, destination):
    marker = json.loads((source / '.last-success.json').read_text())
    name = marker['filename']
    if not NAME.fullmatch(name) or (source / name).is_symlink():
        raise ValueError('Unexpected snapshot name or symbolic link')
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = destination / name
    expected = file_hash(source / name)
    if target.exists():
        if target.is_symlink() or file_hash(target) != expected:
            raise ValueError('Immutable exported snapshot differs')
        return name
    with tempfile.NamedTemporaryFile(dir=destination, prefix='.copy-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            with (source / name).open('rb') as origin:
                shutil.copyfileobj(origin, stream)
            stream.flush()
            os.fsync(stream.fileno())
            if file_hash(temporary) != expected:
                raise ValueError('Snapshot copy checksum differs')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(export(args.source, args.destination))


if __name__ == '__main__':
    main()
