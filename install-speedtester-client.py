#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Install the same SpeedTester release as the native packages, with optional host override."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

REPOSITORY = 'ecarara/SpeedTester'
RELEASES_API_URL = 'https://api.github.com/repos/' + REPOSITORY + '/releases/latest'
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 10000


class InstallationError(RuntimeError):
    pass


def server_origin(value):
    import ipaddress
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if len(value) > 253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in value.rstrip('.').split('.')):
        raise argparse.ArgumentTypeError('Informe somente o hostname/IP do servidor de medição opcional.')
    return value


def check_requirements():
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'aarch64', 'arm64'):
        raise InstallationError('Execute este instalador no servidor Linux amd64 ou arm64 que fará as medições.')
    if os.geteuid() == 0:
        raise InstallationError('Execute como usuário normal, sem sudo.')
    if not sys.stdin.isatty():
        raise InstallationError('Execute em um terminal interativo; baixe o arquivo antes de executá-lo.')
    python = None
    for candidate in ('python3', 'python3.13', 'python3.12', 'python3.11'):
        executable = shutil.which(candidate)
        if executable and subprocess.run([executable, '-c', 'import sys,venv;assert sys.version_info[:2]>=(3,11)'],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            python = executable
            break
    if not python:
        raise InstallationError('Instale Python 3.11 ou posterior com venv antes de continuar.')
    if not shutil.which('iperf3') or not shutil.which('bash') or not shutil.which('systemctl'):
        raise InstallationError('Instale iperf3, bash e systemd pelo gerenciador de pacotes da distribuição.')
    if subprocess.run(['systemctl', '--user', 'show-environment'], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        raise InstallationError('É necessária uma sessão systemd do usuário no servidor Linux.')


def _read_limited(response, limit):
    data = response.read(limit + 1)
    if len(data) > limit:
        raise InstallationError('A resposta excedeu o limite permitido.')
    return data


def _trusted_url(value, *, api=False):
    parsed = urllib.parse.urlsplit(value)
    hostname = (parsed.hostname or '').lower()
    allowed = {'api.github.com'} if api else {'github.com'}
    if not api and (hostname == 'github.com' or hostname.endswith('.githubusercontent.com')):
        allowed = {hostname}
    if (parsed.scheme != 'https' or parsed.username or parsed.password or hostname not in allowed
            or parsed.query or parsed.fragment):
        raise InstallationError('Origem HTTPS inesperada no download do Client.')
    return value


def latest_release(opener=None):
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(
        RELEASES_API_URL,
        headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'SpeedTester-Client-Installer'},
    )
    with opener(request, timeout=30) as response:
        _trusted_url(response.geturl(), api=True)
        payload = json.loads(_read_limited(response, 256 * 1024).decode('utf-8'))
    tag = payload.get('tag_name', '')
    if not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+', tag):
        raise InstallationError('A release mais recente não possui uma versão semântica válida.')
    version = tag[1:]
    names = {asset.get('name'): asset.get('browser_download_url') for asset in payload.get('assets', [])}
    archive_name = f'SpeedTester-{version}.tar.gz'
    for name in (archive_name, 'SHA256SUMS'):
        if not names.get(name):
            raise InstallationError(f'Asset obrigatório ausente na release: {name}.')
        _trusted_url(names[name])
    return version, archive_name, names[archive_name], names['SHA256SUMS']


def download_asset(url, path=None, opener=None):
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(_trusted_url(url), headers={'User-Agent': 'SpeedTester-Client-Installer'})
    with opener(request, timeout=60) as response:
        _trusted_url(response.geturl())
        data = _read_limited(response, MAX_DOWNLOAD_BYTES)
    if path is None:
        return data
    with path.open('xb') as target:
        target.write(data)
    return data


def download_archive(path, release, opener=None):
    version, archive_name, archive_url, checksums_url = release
    checksums = download_asset(checksums_url, opener=opener).decode('utf-8')
    match = re.search(r'(?m)^([0-9a-fA-F]{64})  ' + re.escape(archive_name) + r'$',
                     checksums)
    if not match:
        raise InstallationError('A soma SHA-256 do pacote não foi publicada.')
    data = download_asset(archive_url, opener=opener)
    digest = hashlib.sha256(data).hexdigest()
    if digest.lower() != match.group(1).lower():
        raise InstallationError('Checksum inválido. A instalação foi interrompida antes de executar o pacote.')
    with path.open('xb') as target:
        target.write(data)
    return version

def extract_archive(path, destination, version):
    prefix = 'SpeedTester-' + version
    seen = set()
    with tarfile.open(path, 'r:gz') as archive:
        members = archive.getmembers()
        if len(members) > MAX_MEMBERS or sum(member.size for member in members) > MAX_UNPACKED_BYTES:
            raise InstallationError('Conteúdo do pacote excede os limites permitidos.')
        for member in members:
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != prefix or '..' in parts or '\\' in member.name
                    or member.name.startswith('/') or not (member.isdir() or member.isfile())
                    or member.name in seen):
                raise InstallationError('Caminho ou tipo de arquivo não permitido no pacote.')
            seen.add(member.name)
        # Extract only regular files and directories after validating every entry.
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
            else:
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with archive.extractfile(member) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output)
                target.chmod(0o700 if member.mode & 0o111 else 0o600)
    project = destination / prefix
    for required in ('packaging/linux/install-user.sh', 'packaging/linux/configure-user.sh', 'app/requirements.txt',
                     'app/collector/target_selection.py', 'LICENSE'):
        if not (project / required).is_file():
            raise InstallationError('Pacote incompleto; nenhum instalador foi executado.')
    return project


def install(server=None, port=5201):
    check_requirements()
    previous_umask = os.umask(0o077)
    try:
        release = latest_release()
        print(f'Baixando o SpeedTester Client v{release[0]} e verificando sua integridade…', flush=True)
        with tempfile.TemporaryDirectory(prefix='speedtester-client-install-') as temporary:
            directory = Path(temporary)
            archive = directory / 'client.tar.gz'
            version = download_archive(archive, release)
            project = extract_archive(archive, directory / 'source', version)
            print('Pacote verificado. Confirme o fuso e o servidor automático ou sua escolha opcional…', flush=True)
            environment = os.environ.copy()
            environment['APP_VERSION'] = version
            if server:
                environment.update(SPEEDTESTER_IPERF3_SERVER=server, SPEEDTESTER_IPERF3_PORT=str(port))
            return subprocess.call(['bash', str(project / 'packaging/linux/install-user.sh')], cwd=project, env=environment)
    finally:
        os.umask(previous_umask)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', '--iperf3-server', type=server_origin, default=None,
                        help='Servidor de medição opcional (padrão: automático pela localização geográfica)')
    parser.add_argument('--port', type=int, default=5201, help='Porta do servidor escolhido (padrão: 5201)')
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.port <= 65535:
            raise InstallationError('A porta deve estar entre 1 e 65535.')
        return install(args.server, args.port)
    except (InstallationError, OSError, tarfile.TarError) as exc:
        print('Instalação interrompida: ' + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Instalação interrompida pelo usuário.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
