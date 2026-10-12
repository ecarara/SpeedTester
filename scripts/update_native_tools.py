#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Prepare reviewable native-tool updates from fixed official upstreams."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
GITHUB = 'https://api.github.com/repos/'


def download(url, limit=50 * 1024 * 1024):
    request = urllib.request.Request(url, headers={'User-Agent': 'SpeedTester-dependency-maintenance'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Upstream response exceeds size budget')
    return data


def upstream_json(path):
    return json.loads(download(GITHUB + path, 2 * 1024 * 1024))


def numeric(version):
    return tuple(int(value) for value in re.findall(r'\d+', version))


def replace_archive(text, current, candidate, url):
    if numeric(candidate) <= numeric(current):
        return text
    checksum = hashlib.sha256(download(url)).hexdigest()
    result, count = re.subn(r'ADD --checksum=sha256:[0-9a-f]{64}',
                            'ADD --checksum=sha256:' + checksum, text)
    if count != 1:
        raise ValueError('Expected exactly one source archive checksum')
    return result.replace(current, candidate)


def prepare(root=ROOT):
    backup_path = root / 'docker/backup/Dockerfile'
    collector_path = root / 'docker/collector/Dockerfile'
    backup = backup_path.read_text()
    collector = collector_path.read_text()
    changes = []
    tags = upstream_json('openssh/openssh-portable/tags?per_page=100')
    versions = [tag['name'][2:].replace('_', '.', 1).replace('_P', 'p')
                for tag in tags if re.fullmatch(r'V_\d+_\d+_P\d+', tag['name'])]
    if not versions:
        raise ValueError('No stable OpenSSH portable tag found')
    ssh = max(versions, key=numeric)
    current = re.search(r'openssh-(\d+[.]\d+p\d+)[.]tar[.]gz', backup).group(1)
    backup = replace_archive(backup, current, ssh,
                             'https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-' + ssh + '.tar.gz')
    if numeric(ssh) > numeric(current):
        changes.append(('OpenSSH', current, ssh))
    release = upstream_json('esnet/iperf/releases/latest')
    version = release['tag_name']
    if release.get('prerelease') or release.get('draft') or not re.fullmatch(r'\d+[.]\d+(?:[.]\d+)?', version):
        raise ValueError('Unexpected iPerf3 release')
    current = re.search(r'iperf-(\d+[.]\d+(?:[.]\d+)?)[.]tar[.]gz', collector).group(1)
    collector = replace_archive(collector, current, version,
                                'https://github.com/esnet/iperf/releases/download/' + version + '/iperf-' + version + '.tar.gz')
    if numeric(version) > numeric(current):
        changes.append(('iPerf3', current, version))
    release = upstream_json('FiloSottile/age/releases/latest')
    version = release['tag_name']
    if release.get('prerelease') or release.get('draft') or not re.fullmatch(r'v\d+[.]\d+[.]\d+', version):
        raise ValueError('Unexpected age release')
    current = re.search(r'filippo[.]io/age/cmd/age@v(\d+[.]\d+[.]\d+)', backup).group(1)
    if numeric(version) > numeric(current):
        backup = backup.replace('@v' + current, '@' + version)
        changes.append(('age', current, version[1:]))
    # All upstream data is validated before changing any tracked file.
    backup_path.write_text(backup)
    collector_path.write_text(collector)
    document = root / 'docs/third-party.md'
    text = document.read_text()
    for _, old, new in changes:
        text = text.replace(old, new)
    document.write_text(text)
    return changes


def main():
    changes = prepare()
    print(json.dumps({'updates': [name for name, _, _ in changes]}))


if __name__ == '__main__':
    main()
