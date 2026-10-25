#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise the packaged local API with isolated data and no measurements."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

WINDOWS = sys.platform == 'win32'


def stop_process(process):
    """Also stop a Windows onefile bootloader's API child before removing data."""
    if WINDOWS:
        result = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
            capture_output=True, text=True, timeout=15, check=False)
        if result.returncode and process.poll() is None:
            raise RuntimeError('Could not stop the frozen API process tree: ' + result.stderr)
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def check(executable):
    executable = Path(executable).resolve(strict=True)
    runtime = json.loads(subprocess.check_output(
        [str(executable), '--runtime-info'], text=True, timeout=30))
    assert runtime['python'].startswith('3.14.'), runtime
    assert runtime.get('frozen') is True, runtime
    with tempfile.TemporaryDirectory(prefix='speedtester-frozen-api-') as temporary:
        root = Path(temporary)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        environment = dict(os.environ, DB_PATH=str(root / 'samples.db'),
            MPLCONFIGDIR=str(root / 'mpl'), API_PORT=str(port),
            SPEEDTESTER_LOCAL_MODE='true', API_REQUIRE_LOGIN='false',
            ISP_LOOKUP_ENABLED='false', SPEEDTESTER_CONFIG_FILE=str(root / 'absent.env'))
        # The frozen process must work outside its source/build directory.
        with (root / 'api.log').open('wb') as log:
            process = subprocess.Popen([str(executable)], cwd=root, env=environment,
                stdout=log, stderr=subprocess.STDOUT)
            try:
                base = f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 60
                while True:
                    try:
                        with urllib.request.urlopen(base + '/health', timeout=2) as response:
                            assert response.status == 200
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError((root / 'api.log').read_text(errors='replace'))
                        time.sleep(0.2)
                for path in ('/', '/dashboard/charts.js', '/dashboard/world-map.svg',
                             '/api/config', '/api/summary'):
                    with urllib.request.urlopen(base + path, timeout=15) as response:
                        assert response.status == 200, path
                        assert response.read(), path
                with urllib.request.urlopen(base + '/api/auth/session', timeout=5) as response:
                    session = json.load(response)
                    assert session['login_required'] is False, session
                with urllib.request.urlopen(base + '/api/chart.png', timeout=30) as response:
                    assert response.read(8) == b'\x89PNG\r\n\x1a\n'
            finally:
                stop_process(process)
    print('frozen-api-ok: Python 3.14, local access, dashboard assets, summary and PNG; no measurements')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable', required=True, type=Path)
    check(parser.parse_args().executable)
