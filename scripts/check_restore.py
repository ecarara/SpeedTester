#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Restore a completed snapshot into temporary storage and compare its data."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from restore import restore


def signature(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup integrity failed')
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if 'samples' not in tables:
            raise ValueError('Missing samples table')
        digest = hashlib.sha256()
        counts = {}
        for name in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            counts[name] = 0
            # Hash row representations independent of SQLite's physical pages.
            rows = sorted(hashlib.sha256(repr(row).encode()).digest()
                          for row in db.execute('SELECT * FROM ' + quoted))
            digest.update(name.encode())
            for row in rows:
                counts[name] += 1
                digest.update(row)
        return counts, digest.hexdigest()


def check(source):
    source = Path(source)
    expected = signature(source)
    with tempfile.TemporaryDirectory(prefix='speedtester-recovery-') as temporary:
        target = Path(temporary) / 'restored.db'
        restore(source, target)
        if signature(target) != expected:
            raise ValueError('Restored data differs from snapshot')
    return {'status': 'passed', 'rows': expected[0]['samples'],
            'tables': len(expected[0]), 'data_sha256': expected[1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.source)))


if __name__ == '__main__':
    main()
