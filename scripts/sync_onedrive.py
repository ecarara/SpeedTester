#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Copy snapshots through an operator-configured rclone crypt remote."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sync(folder, config, remote, status):
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError('Backup folder unavailable')
    if not config.is_file() or config.is_symlink() or config.stat().st_mode & 0o077:
        raise ValueError('rclone configuration must be private (0600)')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+:[a-zA-Z0-9/_-]*', remote):
        raise ValueError('Expected a configured remote and relative path')
    name = remote.split(':', 1)[0]
    # Do not put plaintext SQLite backups in the cloud. crypt wraps OneDrive.
    result = subprocess.run(['rclone', '--config', str(config), 'config', 'dump'],
                            capture_output=True, text=True, timeout=30, check=True)
    configuration = json.loads(result.stdout)
    if configuration.get(name, {}).get('type') != 'crypt':
        raise ValueError('Backup destination must be an rclone crypt remote')
    args = ['rclone', '--config', str(config), 'copy', str(folder), remote,
            '--include', 'speedtester-*.db', '--immutable', '--checksum',
            '--transfers', '1', '--checkers', '2', '--retries', '3', '--contimeout', '20s']
    completed = subprocess.run(args, capture_output=True, timeout=1800, check=False)
    if completed.returncode == 0:
        completed = subprocess.run(['rclone', '--config', str(config), 'cryptcheck',
                                    str(folder), remote, '--one-way', '--include', 'speedtester-*.db'],
                                   capture_output=True, timeout=1800, check=False)
    evidence = {'status': 'passed' if completed.returncode == 0 else 'failed', 'checked_at': time.time()}
    temporary = status.with_suffix('.tmp')
    temporary.write_text(json.dumps(evidence))
    temporary.chmod(0o600)
    os.replace(temporary, status)
    if completed.returncode:
        raise RuntimeError('OneDrive copy failed; private configuration and diagnostics withheld')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--remote', required=True)
    parser.add_argument('--status', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    print(json.dumps(sync(args.folder, args.config, args.remote, args.status)))


if __name__ == '__main__':
    main()
