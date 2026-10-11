#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Validate and restore a SQLite backup while every database client is stopped."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile


def restore(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if source == destination:
        raise ValueError('Source and destination must differ')
    if any(Path(str(destination) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Database sidecars are present; stop all services before restoring')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as origin:
        if origin.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Source integrity check failed')
        if not origin.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='samples'").fetchone():
            raise ValueError('Source is not a SpeedTester database')
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.speedtester-restore-', dir=destination.parent)
        os.close(descriptor)
        temporary = Path(name)
        try:
            with closing(sqlite3.connect(temporary)) as target:
                origin.backup(target)
                if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Restored integrity check failed')
            with temporary.open('rb') as handle:
                os.fsync(handle.fileno())
            if destination.exists():
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                previous = destination.with_name(destination.name + '.before-restore-' + stamp)
                # Keep the current database available until the atomic replacement.
                os.link(destination, previous)
                temporary.chmod(destination.stat().st_mode & 0o777)
            os.replace(temporary, destination)
            print('restore-ok; previous database retained when present')
        finally:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--services-stopped', action='store_true', required=True,
                        help='Confirm that API, collector, backup and other SQLite clients are stopped')
    args = parser.parse_args()
    try:
        restore(args.source, args.destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f'restore failed: {exc}\n')


if __name__ == '__main__':
    main()
