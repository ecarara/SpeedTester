#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Read-only preflight for configuration, Docker and optional network access."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from shared.settings import load_settings
from collector.quadrants import local_date_now, plan_day_slots


def load_env(path):
    """Parse literal KEY=value lines; never execute shell substitutions."""
    if not path.is_file():
        raise ValueError('Environment file not found; copy env.example to .env first')
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, separator, raw = line.partition('=')
        if not separator or not key.strip().replace('_', '').isalnum():
            raise ValueError(f'Invalid environment assignment on line {number}')
        parts = shlex.split(raw, comments=True)
        value = ' '.join(parts)
        os.environ.setdefault(key.strip(), value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path('.env'))
    parser.add_argument('--container', action='store_true', help='Check runner binaries instead of host Docker')
    parser.add_argument('--network', action='store_true', help='Probe configured iPerf3 TCP port (no speed measurement)')
    args = parser.parse_args()
    errors = []
    try:
        if not args.container:
            load_env(args.env_file)
        settings = load_settings()
        plan_day_slots(local_date_now(settings.timezone), settings.timezone,
                       settings.measurements_per_quadrant, settings.sample_duration_seconds)
        print('[ok] settings and timezone')
    except (ValueError, KeyError, OSError) as exc:
        print(f'[error] configuration: {exc}', file=sys.stderr)
        return 1
    if settings.speedtest_runner == 'iperf3' and not settings.iperf3_server:
        print('[ok] automatic geographic server selection; IPERF3_SERVER is optional')
    if args.container:
        binary = {'iperf3':'iperf3', 'ookla':settings.ookla_binary}.get(settings.speedtest_runner)
        if binary and not shutil.which(binary):
            errors.append('Selected runner binary is unavailable on this architecture')
    else:
        try:
            for command in (['docker', 'compose', 'version'], ['docker', 'info']):
                subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=True)
            print('[ok] Docker daemon and Compose')
        except (OSError, subprocess.SubprocessError):
            errors.append('Docker Engine and Compose must be installed and accessible to this user')
    if settings.api_require_admin_token and not settings.api_admin_token:
        print('[notice] administrative writes are disabled until API_ADMIN_TOKEN is configured')
    if args.network and settings.iperf3_server:
        try:
            with socket.create_connection((settings.iperf3_server, settings.iperf3_port), timeout=5):
                print('[ok] iPerf3 TCP endpoint is reachable')
        except OSError:
            errors.append('Configured iPerf3 endpoint is unreachable')
    for error in errors:
        print(f'[error] {error}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
