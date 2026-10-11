#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Pull deployment after CI, images and Sonar pass; keep secrets on the host."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.request

REPO = 'ecarara/SpeedTester'
SERVICES = ('api', 'collector', 'backup')
REQUIRED = {'CI', 'Container images', 'SonarQube'}


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'SpeedTester-staging-deploy', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def eligible_revision():
    base = 'https://api.github.com/repos/' + REPO
    sha = fetch_json(base+'/branches/main')['commit']['sha']
    runs = fetch_json(base+'/actions/runs?branch=main&event=push&per_page=100')['workflow_runs']
    latest = {}
    for run in sorted(runs, key=lambda item: item['id'], reverse=True):
        if run['head_sha'] == sha and run['name'] not in latest:
            latest[run['name']] = run
    if all(name in latest and latest[name]['conclusion'] == 'success' for name in REQUIRED):
        return sha
    return None


def run(*args):
    # Docker diagnostics can contain env values. Keep output off journal/public logs.
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f'Command failed: {args[0]} (exit {result.returncode})')
    return result.stdout.strip()


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.chmod(0o600)
    os.replace(temporary, path)


def release_source(root, sha):
    release = root/'releases'/sha
    if release.exists():
        return release
    release.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=release.parent) as temporary:
        archive = Path(temporary)/'source.tar.gz'
        with urllib.request.urlopen('https://api.github.com/repos/'+REPO+'/tarball/'+sha, timeout=60) as response:
            with archive.open('wb') as output:
                while block := response.read(1024*1024):
                    output.write(block)
        extracted = Path(temporary)/'source'
        extracted.mkdir()
        with tarfile.open(archive) as source:
            source.extractall(extracted, filter='data')
        directories = list(extracted.iterdir())
        if len(directories) != 1 or not (directories[0]/'docker/compose.yaml').is_file():
            raise ValueError('Unexpected source archive')
        os.replace(directories[0], release)
    return release


def image_digests(sha):
    result = {}
    for service in SERVICES:
        tag = f'ghcr.io/ecarara/speedtester-{service}:sha-{sha}'
        run('docker', 'pull', tag)
        image = json.loads(run('docker', 'image', 'inspect', tag))[0]
        if image['Config']['Labels'].get('org.opencontainers.image.revision') != sha:
            raise ValueError('Image revision does not match source')
        prefix = f'ghcr.io/ecarara/speedtester-{service}@sha256:'
        digest = next((item for item in image['RepoDigests'] if item.startswith(prefix)), None)
        if not digest:
            raise ValueError('Image digest unavailable')
        result[service] = digest
    return result


def compose_command(root, release, images, project, db_volume, backup_volume, suffix):
    override = root/f'deploy-{suffix}.json'
    save_json(override, {'services': {service: {'image': images[service]} for service in SERVICES},
                       'volumes': {'db_data': {'external': True, 'name': db_volume},
                                   'backup_data': {'external': True, 'name': backup_volume}}})
    return ('docker', 'compose', '--env-file', str(root/'.env'), '-p', project,
            '-f', str(release/'docker/compose.yaml'), '-f', str(override))


def backup_database(root, image, volume, sha):
    directory = root/'deployment-backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'-'+sha+'.db'
    code = "import sqlite3,os;from contextlib import closing;os.umask(0o077)\nwith closing(sqlite3.connect('file:/data/speedtester.db?mode=ro',uri=True)) as source,closing(sqlite3.connect('/snapshots/"+name+"')) as target:\n source.backup(target)\n assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'"
    run('docker', 'run', '--rm', '--network', 'none', '--user', '0', '-v', volume+':/data:ro',
        '-v', str(directory)+':/snapshots', image, 'python', '-c', code)
    return name


def restore_database(root, image, volume, snapshot):
    run('docker', 'run', '--rm', '--network', 'none', '--user', '0', '-v', volume+':/data',
        '-v', str(root/'deployment-backups')+':/snapshots:ro', image, 'sh', '-c',
        'python /opt/speedtester-scripts/restore.py /snapshots/'+snapshot+
        ' --destination /data/speedtester.db --services-stopped && chown 10001:10001 /data/speedtester.db')


def validate_service(command):
    # Check locally inside the container, keeping host addresses and tokens private.
    code = "import json,os,urllib.request;headers={'X-Admin-Token':os.environ.get('API_ADMIN_TOKEN','')};r=urllib.request.Request('http://127.0.0.1:8000/health',headers=headers);d=json.load(urllib.request.urlopen(r,timeout=5));assert d.get('collector',{}).get('status')=='ok'"
    for _ in range(24):
        try:
            run(*command, 'exec', '-T', 'api', 'python', '-c', code)
            return
        except RuntimeError:
            time.sleep(5)
    raise RuntimeError('Collector failed health validation')


def deploy(root, sha, project, db_volume, backup_volume):
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Expected full Git commit SHA')
    state_file = root/'deployment.json'
    previous = json.loads(state_file.read_text()) if state_file.exists() else None
    if previous and previous['revision'] == sha:
        return 'unchanged'
    release = release_source(root, sha)
    images = image_digests(sha)
    if not previous:
        previous = {'release_dir': str(root), 'images': {service: json.loads(run('docker', 'inspect', f'{project}-{service}-1'))[0]['Image'] for service in SERVICES}}
    old = compose_command(root, Path(previous['release_dir']), previous['images'], project, db_volume, backup_volume, 'previous')
    new = compose_command(root, release, images, project, db_volume, backup_volume, 'candidate')
    run(*new, 'config', '--quiet')
    # Pause every SQLite client before the pre-migration snapshot.
    run(*old, 'stop', 'api', 'collector', 'backup')
    snapshot = None
    try:
        snapshot = backup_database(root, images['api'], db_volume, sha)
        run(*new, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        validate_service(new)
        state = {'revision': sha, 'release_dir': str(release), 'images': images, 'backup': snapshot,
                 'deployed_at': datetime.now(timezone.utc).isoformat()}
        save_json(root/'previous-deployment.json', previous)
        save_json(state_file, state)
        return 'deployed'
    except Exception:
        run(*new, 'stop', 'api', 'collector', 'backup')
        if snapshot:
            restore_database(root, images['api'], db_volume, snapshot)
        run(*old, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '180')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--project', default='speedtester')
    parser.add_argument('--db-volume', required=True)
    parser.add_argument('--backup-volume', required=True)
    args = parser.parse_args()
    args.root = args.root.resolve()
    with (args.root/'.deployment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sha = eligible_revision()
        if not sha:
            print('deploy-waiting-for-checks')
            return
        print(deploy(args.root, sha, args.project, args.db_volume, args.backup_volume))


if __name__ == '__main__':
    main()
