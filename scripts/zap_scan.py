#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Active API scan only in a verified CI fixture; passive Baseline elsewhere."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_TOKEN = 'security-fixture-admin'


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.PIPE, text=True).strip()


def verify_fixture(project):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or not re.fullmatch(r'speedtester-security-\d+-\d+', project):
        raise ValueError('Active scans require a disposable GitHub Actions fixture')
    containers = json.loads(command('docker', 'inspect', f'{project}-api-1'))
    container = containers[0]
    env = dict(item.split('=', 1) for item in container['Config']['Env'])
    if env.get('SPEEDTEST_SECURITY_FIXTURE') != 'true' or env.get('API_ADMIN_TOKEN') != FIXTURE_TOKEN:
        raise ValueError('The target is not the synthetic API')
    mounts = [mount for mount in container['Mounts'] if mount['Destination'] == '/data']
    if len(mounts) != 1 or mounts[0]['Type'] != 'volume' or mounts[0]['Name'] != f'{project}_fixture_data':
        raise ValueError('Active scans may only use the disposable database volume')
    network = json.loads(command('docker', 'network', 'inspect', f'{project}_isolated'))[0]
    if not network['Internal']:
        raise ValueError('The active scan network must be isolated')
    code = "import json,urllib.request; r=urllib.request.Request('http://127.0.0.1:8000/api/config',headers={'X-Admin-Token':'security-fixture-admin'});d=json.load(urllib.request.urlopen(r));assert d['demo'] is True"
    command('docker', 'exec', f'{project}-api-1', 'python', '-c', code)


def check_report(path):
    data = json.loads(path.read_text())
    sites = data.get('site')
    if not isinstance(sites, list) or not sites:
        raise ValueError('ZAP produced no target report')
    alerts = [alert for site in sites for alert in site.get('alerts', [])]
    high = [alert for alert in alerts if int(alert['riskcode']) >= 3]
    result = {'status': 'failed' if high else 'passed', 'alerts': len(alerts),
              'high_alerts': len(high), 'gate': 'high', 'scanned_sites': len(sites)}
    (path.parent / 'summary.json').write_text(json.dumps(result, indent=2))
    if high:
        raise ValueError('ZAP high-risk security gate failed')
    return result


def scan(mode, output, project=None, target=None):
    image = json.loads((ROOT / 'security/tools.json').read_text())['zap']['image']
    if mode == 'active':
        verify_fixture(project or '')
    else:
        url = urlsplit(target or '')
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
            raise ValueError('Baseline requires an HTTP(S) target without credentials')
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    uid, gid = (os.getuid(), os.getgid()) if os.getuid() else (1000, 1000)
    if os.geteuid() == 0:
        os.chown(output, uid, gid)
    hook = (ROOT / 'security/zap_runtime_hook.py').read_text()
    if mode == 'active':
        hook += '\n' + (ROOT / 'security/zap_api_hook.py').read_text()
    (output / 'hook.py').write_text(hook)
    base = ['docker', 'run', '--rm', '--name', 'speedtester-zap-' + str(os.getpid()),
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--user', f'{uid}:{gid}', '--workdir', '/zap/wrk', '-e', 'HOME=/zap/wrk/zap-home',
            '--memory', '1g', '--cpus', '1', '--pids-limit', '256',
            '-v', str(output.resolve()) + ':/zap/wrk:Z']
    if mode == 'active':
        code = "import json,urllib.request;r=urllib.request.Request('http://127.0.0.1:8000/openapi.json',headers={'X-Admin-Token':'security-fixture-admin'});d=json.load(urllib.request.urlopen(r));d['servers']=[{'url':'http://api:8000'}];print(json.dumps(d))"
        (output / 'openapi.json').write_text(command('docker', 'exec', f'{project}-api-1', 'python', '-c', code))
        scan_args = ['--network', f'{project}_isolated', image, 'zap-api-scan.py',
                     '-t', '/zap/wrk/openapi.json', '-f', 'openapi']
    else:
        # Only this packaged passive scan is reachable from the staging mode.
        scan_args = ['--network', 'host', image, 'zap-baseline.py', '-t', target, '-m', '1', '--autooff']
    if os.geteuid() == 0:
        for file in output.iterdir():
            os.chown(file, uid, gid)
    args = base + scan_args + ['--hook', '/zap/wrk/hook.py', '-I', '-T', '5', '-J', 'zap.json', '-r', 'zap.html', '-s',
                             '-z', '-silent -dir /zap/wrk/zap-home -host 127.0.0.1 '
                             '-config api.addrs.addr.name=^(127[.]0[.]0[.]1|localhost|zap)$ '
                             '-config api.addrs.addr.regex=true '
                             '-config ascan.maxScanDurationInMins=10']
    try:
        with (output / 'execution.log').open('w') as log:
            completed = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                                       timeout=1200 if mode == 'active' else 420, check=False)
        if completed.returncode not in (0, 2):
            raise RuntimeError('ZAP execution failed; consult the private execution log')
        return check_report(output / 'zap.json')
    finally:
        subprocess.run(['docker', 'rm', '-f', 'speedtester-zap-' + str(os.getpid())],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('active', 'baseline'))
    parser.add_argument('--project')
    parser.add_argument('--target')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    if args.mode == 'active' and args.target:
        parser.error('Active target is fixed to the disposable API')
    result = scan(args.mode, args.output, args.project, args.target)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
