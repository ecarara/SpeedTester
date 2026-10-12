#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Remove only expired owned artifacts, preserving current/rollback evidence."""
import argparse
import json
from pathlib import Path
import re
import shutil
import time


PATTERNS = {
    'releases': re.compile(r'[0-9a-f]{40}'),
    'deployment-backups': re.compile(r'\d{8}T\d{12}-[0-9a-f]{40}[.]db'),
    'reports': re.compile(r'(?:\d{8}T\d{12}|recheck-\d{8}T\d{6}Z)-[0-9a-f]{40}'),
    'outbox': re.compile(r'speedtester-\d{8}T\d{6}Z-\d+[.]db'),
}


def prune(directory, pattern, days, protected=(), now=None):
    if not 7 <= days <= 3650 or directory.is_symlink():
        raise ValueError('Retention must be 7..3650 days in an owned directory')
    cutoff = (time.time() if now is None else now) - days * 86400
    removed = []
    if not directory.exists():
        return removed
    for path in directory.iterdir():
        if path.name in protected or path.is_symlink() or not pattern.fullmatch(path.name):
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path.name)
    return removed


def cleanup(root, reports, outbox, days=30, now=None):
    protected = set()
    for name in ('deployment.json', 'previous-deployment.json'):
        path = root / name
        if path.exists():
            state = json.loads(path.read_text())
            protected.update((state.get('revision'), state.get('backup')))
            evidence = state.get('security', {}).get('baseline_report')
            if evidence:
                protected.add(Path(evidence).name)
    results = {}
    for name, directory in (('releases', root / 'releases'), ('deployment-backups', root / 'deployment-backups'),
                            ('reports', reports)):
        results[name] = prune(directory, PATTERNS[name], days, protected, now)
    # Do not evict pending exports until a verified OneDrive copy exists.
    status = outbox / '.sync-status.json'
    results['outbox'] = []
    if status.exists() and json.loads(status.read_text()).get('status') == 'passed':
        completed_at = json.loads(status.read_text())['checked_at']
        keep = [p.name for p in outbox.iterdir() if p.stat().st_mtime > completed_at]
        results['outbox'] = prune(outbox, PATTERNS['outbox'], days, keep, now)
    return {key: len(value) for key, value in results.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--outbox', type=Path, required=True)
    parser.add_argument('--days', type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(cleanup(args.root, args.reports, args.outbox, args.days)))


if __name__ == '__main__':
    main()
