#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Gate complete Grype JSON reports without removing unresolved findings."""
import argparse
import json
from pathlib import Path


def check_report(path):
    data = json.loads(path.read_text())
    if not isinstance(data.get('matches'), list) or not data.get('descriptor', {}).get('db', {}).get('status'):
        raise ValueError('Missing Grype findings or database evidence')
    if data['descriptor']['db']['status'].get('valid') is not True:
        raise ValueError('Grype database is not valid')
    blocking = []
    for match in data['matches']:
        vulnerability = match['vulnerability']
        severity = vulnerability['severity']
        fix = vulnerability.get('fix', {})
        if severity == 'Critical' or (severity == 'High' and fix.get('state') == 'fixed' and fix.get('versions')):
            blocking.append(vulnerability['id'])
    summary = {'findings': len(data['matches']), 'blocking_findings': len(blocking),
               'policy': 'all Critical and High with an available fix',
               'status': 'failed' if blocking else 'passed'}
    path.with_suffix('.summary.json').write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    args = parser.parse_args()
    summaries = [check_report(path) for path in args.reports]
    print(json.dumps(summaries))
    if any(item['blocking_findings'] for item in summaries):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
