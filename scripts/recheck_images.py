#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Re-evaluate immutable images with current Grype data and the approved gate."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from check_image_report import check_report


def scan(images, output, executable='grype', platforms=('linux/amd64', 'linux/arm64')):
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    summaries = []
    for service, image in sorted(images.items()):
        if not re.fullmatch(r'ghcr.io/ecarara/speedtester-(api|collector|backup)@sha256:[0-9a-f]{64}', image):
            raise ValueError('Expected a SpeedTester immutable digest')
        if service not in {'api', 'collector', 'backup'}:
            raise ValueError('Unexpected service')
        for platform in platforms:
            if platform not in {'linux/amd64', 'linux/arm64'}:
                raise ValueError('Unexpected platform')
            path = output / (service + '-' + platform.split('/')[1] + '.json')
            with path.open('w') as report:
                result = subprocess.run([executable, 'registry:' + image, '--platform', platform, '-o', 'json'],
                                        stdout=report, stderr=subprocess.PIPE, timeout=600, check=False,
                                        env={**os.environ, 'GRYPE_DB_AUTO_UPDATE': 'true',
                                             'GRYPE_DB_VALIDATE_AGE': 'true', 'GRYPE_DB_MAX_ALLOWED_BUILT_AGE': '24h'})
            if result.returncode:
                raise RuntimeError('Image recheck failed; existing services left running')
            summaries.append({'service': service, 'platform': platform, **check_report(path)})
    if len(images) != 3:
        raise ValueError('Expected all three service images')
    summary = {'status': 'failed' if any(item['blocking_findings'] for item in summaries) else 'passed',
               'checked_at': datetime.now(timezone.utc).isoformat(), 'images': images, 'reports': summaries}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--grype', default='grype')
    parser.add_argument('--status-file', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    summary = scan(json.loads(args.state.read_text())['images'], args.output, args.grype)
    if args.status_file:
        temporary = args.status_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(summary))
        os.replace(temporary, args.status_file)
    print(json.dumps({'status': summary['status'], 'reports': len(summary['reports'])}))
    if summary['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
