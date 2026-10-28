#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Install and verify the staging HTTPS configuration.

The certificate and private key are host secrets and must be restored separately.
Run prepare before starting the stack on a freshly provisioned staging host.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
from string import Template
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path('/opt/speedtester')
NGINX_CONFIG = Path('/etc/nginx/conf.d/speedtester-https.conf')
DEPLOY_CONFIG = Path('/etc/speedtester-deploy.conf')
PROFILE = Path('/etc/speedtester-staging-https.json')
TEMPLATE = Path(__file__).resolve().parent.parent / 'ops/staging/nginx-https.conf.example'
ENV_VALUES = {'API_PORT': '18000', 'API_BIND_ADDRESS': '127.0.0.1', 'API_COOKIE_SECURE': 'true'}


def load_profile(path=PROFILE):
    """Read host-specific parameters from a trusted local configuration file."""
    mode = path.stat().st_mode
    if mode & 0o022 or (os.geteuid() == 0 and path.stat().st_uid != 0):
        raise ValueError('The staging HTTPS profile must be owned by root and not writable by other users')
    profile = json.loads(path.read_text())
    if set(profile) != {'domain', 'listen_address', 'certificate', 'private_key'}:
        raise ValueError('Unexpected staging HTTPS profile fields')
    domain = profile['domain']
    if not isinstance(domain, str) or not re.fullmatch(r'(?=.{1,253}$)[a-zA-Z0-9]+(?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9]+(?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+', domain):
        raise ValueError('Invalid HTTPS domain')
    address = ipaddress.ip_address(profile['listen_address'])
    if address.version != 4 or address.is_unspecified or address.is_multicast:
        raise ValueError('A specific IPv4 listen address is required')
    for key in ('certificate', 'private_key'):
        value = profile[key]
        if not isinstance(value, str) or not re.fullmatch(r'/[A-Za-z0-9_./-]+', value) or '..' in Path(value).parts:
            raise ValueError('Invalid certificate path')
    return profile


def render(profile):
    return Template(TEMPLATE.read_text()).substitute(profile)


def urls(profile):
    return 'http://' + profile['listen_address'] + ':8000', 'https://' + profile['domain']


def update_assignments(content, values):
    """Preserve unrelated values and remove duplicate managed assignments."""
    lines, found = [], set()
    for line in content.splitlines():
        key = line.partition('=')[0].strip()
        if key in values:
            if key not in found:
                lines.append(f'{key}={values[key]}')
                found.add(key)
        else:
            lines.append(line)
    lines.extend(f'{key}={value}' for key, value in values.items() if key not in found)
    return '\n'.join(lines) + '\n'


def atomic_write(path, text):
    """Preserve ownership and mode; never print the contents of configuration."""
    stat = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(prefix='.speedtester-', dir=path.parent)
    try:
        os.fchmod(fd, stat.st_mode & 0o777 if stat else 0o600)
        if stat:
            os.fchown(fd, stat.st_uid, stat.st_gid)
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if shutil.which('restorecon'):
            subprocess.run(['restorecon', str(path)], check=True)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=30)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed (exit {result.returncode})')
    return result.stdout


def port_type(output, port):
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[1] != 'tcp':
            continue
        for item in ''.join(fields[2:]).split(','):
            ends = item.split('-')
            if all(part.isdigit() for part in ends) and int(ends[0]) <= port <= int(ends[-1]):
                return fields[0]
    return None


def restore_configuration(originals, applied_port):
    for path, original in originals.items():
        if original is None:
            path.unlink(missing_ok=True)
        elif not path.exists() or path.read_text() != original:
            atomic_write(path, original)
    if applied_port:
        run('semanage', 'port', '-d', '-p', 'tcp', '8000')
    run('nginx', '-t')
    run('systemctl', 'reload', 'nginx')


def prepare(root=ROOT, nginx_config=NGINX_CONFIG, deploy_config=DEPLOY_CONFIG):
    """Reconcile host files and SELinux; never create credentials or certificates."""
    profile = load_profile()
    if not (Path(profile['certificate']).is_file() and Path(profile['private_key']).is_file()):
        raise RuntimeError('Restore the staging certificate and private key first')
    env_path = root / '.env'
    if not env_path.is_file() or not deploy_config.is_file():
        raise RuntimeError('Create the staging .env and deploy configuration first')
    originals = {p: p.read_text() if p.exists() else None for p in (env_path, nginx_config, deploy_config)}
    new_env = update_assignments(originals[env_path], ENV_VALUES)
    new_deploy = update_assignments(originals[deploy_config], {
        'STAGING_BASELINE_URL': 'http://127.0.0.1:18000/',
        'SPEEDTESTER_STAGING_HTTPS_CHECK': 'true',
    })
    new_nginx = render(profile)
    # The active API must not own the redirect port when nginx reloads.
    if new_env != originals[env_path] and (profile['listen_address'] + ':8000') in run('ss', '-ltn'):
        raise RuntimeError('Stop the old API before moving the HTTP port; retain its data volumes')
    if run('getenforce').strip() != 'Enforcing':
        raise RuntimeError('This staging profile requires SELinux enforcing')
    current = port_type(run('semanage', 'port', '-l'), 8000)
    custom = port_type(run('semanage', 'port', '-l', '-C'), 8000)
    if custom and custom != 'http_port_t':
        raise RuntimeError('Port 8000 has a conflicting local SELinux rule')
    changed_port = current != 'http_port_t'
    applied_port = False
    try:
        if changed_port:
            run('semanage', 'port', '-m' if current else '-a', '-t', 'http_port_t', '-p', 'tcp', '8000')
            applied_port = True
        if new_env != originals[env_path]:
            atomic_write(env_path, new_env)
        if new_deploy != originals[deploy_config]:
            atomic_write(deploy_config, new_deploy)
        if new_nginx != originals[nginx_config]:
            atomic_write(nginx_config, new_nginx)
            run('nginx', '-t')
            run('systemctl', 'reload', 'nginx')
    except Exception:
        restore_configuration(originals, applied_port)
        raise


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify(root=ROOT, nginx_config=NGINX_CONFIG):
    """Reject configuration drift and confirm the live redirect and TLS health."""
    profile = load_profile()
    http_url, https_url = urls(profile)
    actual = (root / '.env').read_text()
    if update_assignments(actual, ENV_VALUES) != actual:
        raise RuntimeError('Staging API binding or secure cookie configuration differs')
    if nginx_config.read_text() != render(profile):
        raise RuntimeError('Staging nginx configuration differs from the versioned profile')
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        direct.open(http_url + '/login?check=1', timeout=10)
    except urllib.error.HTTPError as error:
        try:
            if error.code != 308 or error.headers.get('Location') != https_url + '/login?check=1':
                raise RuntimeError('Unexpected staging redirect') from error
        finally:
            error.close()
    else:
        raise RuntimeError('Staging did not redirect HTTP to HTTPS')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(https_url + '/health', timeout=10) as response:
        if response.status != 200 or json.load(response).get('status') != 'alive':
            raise RuntimeError('Staging HTTPS health check failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify'))
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.root)
    else:
        # nginx reload is asynchronous; allow workers a short time to converge.
        for attempt in range(10):
            try:
                verify(args.root)
                break
            except (OSError, RuntimeError):
                if attempt == 9:
                    raise
                time.sleep(1)
    print('Staging HTTPS ' + args.action + ' completed')


if __name__ == '__main__':
    main()
