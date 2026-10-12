#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Host maintenance holds the deployment lock and writes private evidence."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import time

from operations import load_json, private_json, recovery
from recheck_images import scan
from retention import cleanup
from sync_onedrive import sync


def recheck(root, reports, state_dir):
    state = load_json(root / 'deployment.json')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    evidence = {'status': 'failed', 'checked_at': time.time()}
    try:
        evidence = scan(state['images'], reports / ('recheck-' + stamp + '-' + state['revision']))
        return evidence
    finally:
        private_json(state_dir / 'images.json', evidence)


def backup(root, volume, state_dir, outbox, reports):
    evidence = recovery(root, volume, state_dir, outbox)
    remote = os.environ.get('ONEDRIVE_REMOTE')
    if remote:
        sync(outbox, Path(os.environ['RCLONE_CONFIG']), remote, outbox / '.sync-status.json')
    cleanup(root, reports, outbox, int(os.environ.get('ARTIFACT_RETENTION_DAYS', '30')))
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('recheck', 'backup'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--backup-volume', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    parser.add_argument('--outbox', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    # Exclusive lock also protects cleanup from deleting an in-use release.
    with (args.root / '.deployment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.mode == 'recheck':
            evidence = recheck(args.root, args.reports, args.state_dir)
        else:
            evidence = backup(args.root, args.backup_volume, args.state_dir, args.outbox, args.reports)
        print(json.dumps({'status': evidence['status']}))
        if evidence['status'] != 'passed':
            raise SystemExit(1)


if __name__ == '__main__':
    main()
