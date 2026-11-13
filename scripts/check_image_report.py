#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Gate complete Grype JSON reports without removing unresolved findings."""
import argparse
from datetime import date
import json
from pathlib import Path

# Reviewed, temporary risk acceptances. Each entry must name the upstream fix
# that removes it; after "expires" the exemption is ignored on purpose, so it
# cannot silently outlive the planned update.
EXEMPTIONS = {
    'CVE-2026-119170': {
        'package': 'python',
        'expires': '2026-12-08',
        'reason': 'Python 3.14.11 fixes the FIPS hashlib regression; no official image ships it yet (PEP 745 schedules 3.14.11 for 2026-12-01).',
    },
}


def _exemption(match, today):
    vulnerability = match['vulnerability']
    entry = EXEMPTIONS.get(vulnerability['id'])
    if not entry or today > date.fromisoformat(entry['expires']):
        return None
    artifact = match.get('artifact') or {}
    if entry.get('package') and artifact.get('name') != entry['package']:
        return None
    return entry


def check_report(path, today=None):
    data = json.loads(path.read_text())
    if not isinstance(data.get('matches'), list) or not data.get('descriptor', {}).get('db', {}).get('status'):
        raise ValueError('Missing Grype findings or database evidence')
    if data['descriptor']['db']['status'].get('valid') is not True:
        raise ValueError('Grype database is not valid')
    blocking, exemptions, expired = [], [], []
    for match in data['matches']:
        vulnerability = match['vulnerability']
        severity = vulnerability['severity']
        fix = vulnerability.get('fix', {})
        if severity == 'Critical' or (severity == 'High' and fix.get('state') == 'fixed' and fix.get('versions')):
            entry = _exemption(match, today or date.today())
            if entry:
                exemptions.append({'id': vulnerability['id'], 'expires': entry['expires'], 'reason': entry['reason']})
            else:
                blocking.append(vulnerability['id'])
                if vulnerability['id'] in EXEMPTIONS:
                    expired.append(vulnerability['id'])
    summary = {'findings': len(data['matches']), 'blocking_findings': len(blocking),
               'policy': 'all Critical and High with an available fix',
               'exemptions': exemptions, 'expired_exemptions': expired,
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
