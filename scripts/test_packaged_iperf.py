#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Actual packaged iPerf3, RSA and transfer capture against loopback fixtures only."""
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from speedtester_protocol.runner import IperfRunner


def _observe_listener(child, event):
    for line in child.stdout:
        if 'Server listening on' in line:event.set()


def main():
    system=platform.system()
    bundle=ROOT/'dist/desktop/raw'/('SpeedTesterClient.app' if system=='Darwin' else 'SpeedTesterClient')
    tools=bundle/('Contents/MacOS/tools' if system=='Darwin' else 'tools')
    binary=tools/('iperf3.exe' if system=='Windows' else 'iperf3')
    inventory=json.loads((bundle/'iperf-components.json').read_text())
    for name,checksum in inventory['files'].items():
        assert hashlib.sha256((tools/name).read_bytes()).hexdigest()==checksum
    assert inventory['rsa_authentication']
    # Prevent accidental use outside a disposable hosted VM; standalone local
    # runs must explicitly opt in to loopback-only fixture tests.
    assert (os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted') or os.environ.get('SPEEDTESTER_LOOPBACK_FIXTURES')=='1'
    children=[]
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        private=root/'private.pem';private.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        private.chmod(0o600)
        username='00000000-0000-4000-8000-000000000001';password=secrets.token_urlsafe(32)
        users=root/'users.csv';users.write_text(username+','+hashlib.sha256(('{'+username+'}'+password).encode()).hexdigest()+'\n');users.chmod(0o600)
        ports=[]
        try:
            for _ in range(2):
                with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
                ports.append(port)
                options={'creationflags':subprocess.CREATE_NO_WINDOW} if system=='Windows' else {}
                process=subprocess.Popen([str(binary),'--server','--one-off','--bind','127.0.0.1','--port',str(port),
                    '--rsa-private-key-path',private.as_posix(),'--authorized-users-path',users.as_posix(),'--forceflush'],
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,**options)
                children.append(process)
                ready=threading.Event()
                threading.Thread(target=_observe_listener,args=(process,ready),daemon=True).start()
                assert ready.wait(10),'Loopback server did not become ready'
            access=SimpleNamespace(upload_port=ports[0],download_port=ports[1],username=username,password=password,
                rsa_public_key=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode(),expires_at=int(time.time())+30)
            grant=SimpleNamespace(runner='iperf3',target_id='loopback-only',target_scope='lan',max_bytes=8192,max_duration_ms=30000)
            runner=IperfRunner('127.0.0.1',binary=str(binary),target_id='loopback-only',target_scope='lan',authorize=lambda _grant:access)
            result=runner(grant)
            assert result.transfer_bytes==8192
            assert result.upload_mbps>=0
            assert result.download_mbps>=0
            for process in children:assert process.wait(timeout=10)==0
            # Per-attempt one-off listeners are gone; no second transfer can run.
            for port in ports:
                with socket.socket() as check:
                    check.settimeout(.5)
                    assert check.connect_ex(('127.0.0.1',port))!=0
        finally:
            for process in children:
                if process.poll() is None:process.kill()
                process.wait(timeout=5)
                process.stdout.close()
    report={'platform':system,'version':'3.22','rsa_authenticated':True,'bundled_dependency_hashes_verified':True,
        'controlled_loopback_directions':2,'controlled_loopback_payload_bytes':8192,'one_off_endpoints_closed':True,'operational_measurements':0}
    (ROOT/'dist/desktop/acceptance-iperf.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Packaged iPerf3 RSA upload/download and one-off teardown passed on loopback; zero operational measurements')


if __name__=='__main__':main()
