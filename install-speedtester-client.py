#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Download one verified public Client revision and run its guided installer."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

CLIENT_REVISION = '315d35c756c8ec125b6b04027ffb7a3ff581b363'
ARCHIVE_SHA256 = '05220fd88c4060cbeeb53f624f8ddd9fe99e392696dee80ca4ff0afd5ce5c0c6'
ARCHIVE_URL = 'https://codeload.github.com/ecarara/SpeedTester/tar.gz/' + CLIENT_REVISION
DEFAULT_SERVER = 'https://speedtester.cararalab.com.br'
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
MAX_UNPACKED_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 10000


class InstallationError(RuntimeError):
    pass


def server_origin(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError('Informe a origem HTTPS do Server, sem caminho ou credenciais.')
    return value.rstrip('/')


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
        if executable and subprocess.run([executable, '-c', 'import sys,venv;assert (3,11)<=sys.version_info[:2]<=(3,13)'],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            python = executable
            break
    if not python:
        raise InstallationError('Instale Python 3.11, 3.12 ou 3.13 com venv antes de continuar.')
    if not shutil.which('iperf3') or not shutil.which('bash') or not shutil.which('systemctl'):
        raise InstallationError('Instale iperf3, bash e systemd pelo gerenciador de pacotes da distribuição.')
    if subprocess.run(['systemctl', '--user', 'show-environment'], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode:
        raise InstallationError('É necessária uma sessão systemd do usuário no servidor Linux.')


def download_archive(path, opener=None):
    request = urllib.request.Request(ARCHIVE_URL, headers={'User-Agent': 'SpeedTester-Client-Installer'})
    opener = opener or urllib.request.urlopen
    count = 0
    checksum = hashlib.sha256()
    with opener(request, timeout=60) as response, path.open('xb') as target:
        url = urllib.parse.urlsplit(response.geturl())
        if url.scheme != 'https' or url.hostname != 'codeload.github.com':
            raise InstallationError('Origem inesperada no download do Client.')
        while block := response.read(1024 * 1024):
            count += len(block)
            if count > MAX_DOWNLOAD_BYTES:
                raise InstallationError('O pacote excedeu o tamanho máximo permitido.')
            checksum.update(block)
            target.write(block)
    if checksum.hexdigest() != ARCHIVE_SHA256:
        raise InstallationError('Checksum inválido. A instalação foi interrompida antes de executar o pacote.')


def extract_archive(path, destination):
    prefix = 'SpeedTester-' + CLIENT_REVISION
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
    project = destination / prefix
    for required in ('install-community.sh', 'pyproject.toml', 'app/requirements-community.txt',
                     'app/speedtester_protocol/cli.py', 'LICENSE'):
        if not (project / required).is_file():
            raise InstallationError('Pacote incompleto; nenhum instalador foi executado.')
    return project


def install(server):
    check_requirements()
    previous_umask = os.umask(0o077)
    try:
        print('Baixando o SpeedTester Client e verificando sua integridade…', flush=True)
        with tempfile.TemporaryDirectory(prefix='speedtester-client-install-') as temporary:
            directory = Path(temporary)
            archive = directory / 'client.tar.gz'
            download_archive(archive)
            project = extract_archive(archive, directory / 'source')
            print('Pacote verificado. Iniciando configuração e pareamento…', flush=True)
            return subprocess.call(['bash', str(project / 'install-community.sh'), '--server', server], cwd=project)
    finally:
        os.umask(previous_umask)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=server_origin, default=DEFAULT_SERVER,
                        help='Server HTTPS (padrão: %(default)s)')
    args = parser.parse_args(argv)
    try:
        return install(args.server)
    except (InstallationError, OSError, tarfile.TarError) as exc:
        print('Instalação interrompida: ' + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Instalação interrompida pelo usuário.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
