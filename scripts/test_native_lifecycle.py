#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""DESTRUCTIVE acceptance test restricted to fresh disposable GitHub-hosted VMs.

Uses the real frozen helper and OS service manager. Never pairs, requests a grant,
or enables measurements. Refuses to touch any pre-existing installation.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
from speedtester_protocol.native_services import native_layout, SERVICE, LABEL, stop_service, start_service, verify_database
from speedtester_protocol.local_control import ControlClient
from speedtester_protocol.local_security import private_directory, private_open
from speedtester_protocol.queue import EncryptedQueue


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise RuntimeError('Only a disposable GitHub-hosted VM may run this test')
    if os.name!='nt' and os.geteuid()!=0:
        raise RuntimeError('Run acceptance with sudo on the disposable VM')
    layout=native_layout()
    if layout.runtime.exists() or layout.state.exists() or (layout.definition and layout.definition.exists()):
        raise RuntimeError('Refusing to touch a pre-existing installation')
    if layout.system=='Windows':
        import win32serviceutil
        import pywintypes
        try:win32serviceutil.QueryServiceStatus(SERVICE)
        except pywintypes.error as exc:
            if exc.winerror!=1060:raise
        else:raise RuntimeError('Pre-existing service')
    if layout.system=='Linux':
        # Hosted images deliberately make /opt writable for tool installation.
        # Restore normal host permissions only in this disposable VM; the real
        # installer must continue rejecting insecure parents on user machines.
        os.chown('/opt',0,0)
        os.chmod('/opt',0o755)
    bundle=ROOT/'dist/desktop/raw'/('SpeedTesterClient.app' if layout.system=='Darwin' else 'SpeedTesterClient')
    executable=bundle/('Contents/MacOS/SpeedTesterClient' if layout.system=='Darwin' else 'SpeedTesterClient.exe' if os.name=='nt' else 'SpeedTesterClient')
    key=secrets.token_bytes(32)
    client=ControlClient(key,timeout=3)
    passed=[]
    def status():
        result=client.call('status')
        assert result['ok'] and result['service']=='running'
        assert not result['measurements_enabled'] and not result['paired']
        return result
    with tempfile.TemporaryDirectory() as temporary:
        temporary=private_directory(Path(temporary).resolve())
        def native(operation,purge=False):
            path=temporary/'request.json'
            with os.fdopen(private_open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC),'w') as stream:
                json.dump({'operation':operation,'control_key':key.hex(),'purge':purge},stream)
            result=subprocess.run([str(executable),'--native-helper',str(path)],timeout=180,capture_output=True)
            assert result.returncode==0, f'{operation}: helper exit {result.returncode}; '+result.stderr.decode(errors='replace')[-2048:]
        def removed():
            if layout.definition:
                assert not layout.definition.exists()
            try:
                connection=socket.create_connection(('127.0.0.1',45873),timeout=1)
            except OSError:
                pass
            else:
                connection.close()
                raise AssertionError('Control listener survived service removal')
            if layout.system=='Windows':
                import pywintypes
                import win32serviceutil
                try:win32serviceutil.QueryServiceStatus(SERVICE)
                except pywintypes.error as exc:assert exc.winerror==1060
                else:raise AssertionError('SCM service survived removal')
            elif layout.system=='Darwin':
                assert subprocess.run(['/bin/launchctl','print','system/'+LABEL],capture_output=True).returncode!=0
            else:
                assert subprocess.run(['/usr/bin/systemctl','is-enabled',layout.definition.name],capture_output=True).returncode!=0
        def check_state():
            directory=layout.state/'queue'
            verify_database(directory)
            cipher=object.__new__(EncryptedQueue)
            cipher.key=(directory/'storage.key').read_bytes()
            with closing(sqlite3.connect((directory/'index.sqlite').as_uri()+'?mode=ro',uri=True)) as db:
                value=db.execute('SELECT ciphertext FROM entries WHERE id=?',('synthetic-ci-record',)).fetchone()[0]
                assert cipher.open(value,'synthetic-ci-record:ci-evidence')=={'id':'synthetic-ci-record','metric':123}
                assert hashlib.sha256(value).hexdigest()==evidence_hash
            assert digest(directory/'storage.key')==key_hash
            assert digest(layout.state/'service.json')==bootstrap_hash
        try:
            native('install');status();passed.append('real_install_unprivileged_service_and_ipc')
            profile={'version':1,'operator':'Synthetic CI','country_code':'ZZ','region':'CI','city':'CI',
                'access_type':'unknown','link_type':'ethernet'}
            assert client.call('configure',{'origin':'https://server.invalid','profile':profile,
                'timezone':'America/Sao_Paulo','contribute':False})['ok']
            status();passed.append('opt_out_never_pairs_or_enables')
            if layout.system=='Linux':
                subprocess.run(['/usr/bin/systemctl','is-enabled',layout.definition.name],check=True,capture_output=True)
                actual=subprocess.check_output(['/usr/bin/systemctl','show',layout.definition.name,'--property=User','--value'],text=True).strip()
                assert actual==layout.user
            elif layout.system=='Darwin':
                import plistlib
                definition=plistlib.loads(layout.definition.read_bytes())
                assert definition['RunAtLoad'] and definition['UserName']==layout.user
                assert subprocess.run(['/bin/launchctl','print','system/'+LABEL],capture_output=True).returncode==0
            else:
                import win32service
                handle=win32service.OpenSCManager(None,None,win32service.SC_MANAGER_CONNECT)
                service=win32service.OpenService(handle,SERVICE,win32service.SERVICE_QUERY_CONFIG)
                config=win32service.QueryServiceConfig(service)
                win32service.CloseServiceHandle(service);win32service.CloseServiceHandle(handle)
                assert config[1]==win32service.SERVICE_AUTO_START and config[7]==layout.user
            passed.append('real_autostart_configuration_and_dedicated_identity')
            stop_service(layout)
            directory=layout.state/'queue'
            cipher=object.__new__(EncryptedQueue)
            cipher.key=(directory/'storage.key').read_bytes()
            evidence=cipher.seal({'id':'synthetic-ci-record','metric':123},'synthetic-ci-record:ci-evidence')
            with closing(sqlite3.connect(directory/'index.sqlite')) as db:
                with db:
                    db.execute('INSERT INTO entries(id,ciphertext,destination) VALUES(?,?,?)',('synthetic-ci-record',evidence,'ci-evidence'))
            evidence_hash=hashlib.sha256(evidence).hexdigest()
            key_hash=digest(directory/'storage.key');bootstrap_hash=digest(layout.state/'service.json')
            start_service(layout)
            deadline=time.monotonic()+30
            while True:
                try:status();break
                except OSError:
                    assert time.monotonic()<deadline;time.sleep(.25)
            passed.append('real_stop_start_preserves_opt_out')
            saved_configuration=status()['configuration']
            native('install');check_state()
            assert status()['configuration']==saved_configuration
            passed.append('real_upgrade_preserves_configuration_keys_queue_and_opt_out')
            native('repair');status();check_state()
            backups=list((layout.state/'backups').iterdir())
            assert backups
            for backup in backups:verify_database(backup)
            passed.append('real_repair_preserves_ciphertext_keys_pending_queue_and_backup')
            native('uninstall');removed();assert not layout.runtime.exists() and layout.state.exists()
            check_state();passed.append('real_uninstall_preserves_data')
            native('install');status();check_state();passed.append('real_reinstall_preserves_evidence')
            native('uninstall');removed();assert not layout.runtime.exists() and layout.state.exists()
            native('uninstall',True);removed()
            assert not layout.runtime.exists() and not layout.state.exists()
            if layout.definition:assert not layout.definition.exists()
            passed.append('real_uninstall_purge')
        finally:
            if layout.runtime.exists() and (layout.state/'service.json').exists():
                native('uninstall',True)
    report={'platform':platform.system(),'passed':passed,'measurements':0,
        'not_exercised':['interactive elevation dialogs','physical reboot or user logout','public Server account and legal acceptance']}
    destination=ROOT/'dist/desktop/acceptance-native.json'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
