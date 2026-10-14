# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Public unit contract, protected installation and actual subprocess adapter."""
import contextlib,io,json,os,secrets,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from speedtester_protocol.crypto import b64,public_bytes,digest,sign,check_dpop
from speedtester_protocol.models import PairingRequest,Pairing,CredentialBundle,PairingApproval,Grant
from speedtester_protocol.client import ProtocolError
from speedtester_protocol.enrollment import Credentials,PairingClient
from speedtester_protocol.installation import protected_queue,systemd_unit
from speedtester_protocol.cli import discover,exclusive,main
from speedtester_protocol.runner import IperfRunner


class CommunityInstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name).resolve()
        self.queue=protected_queue(self.directory/'state')
        self.possession,self.measurement,self.server=(Ed25519PrivateKey.generate() for _ in range(3))
        self.origin='https://server.example'

    def bundle(self,request_id):
        now=int(time.time())
        return CredentialBundle(client_id=str(uuid4()),access_token=secrets.token_urlsafe(32),refresh_token=secrets.token_urlsafe(32),expires_at=now+900,refresh_expires_at=now+30*86400,nonce=secrets.token_urlsafe(32),possession_key=b64(public_bytes(self.possession)),request_id=request_id)

    def test_public_pairing_consumer_real_signatures_proofs_and_strict_bindings(self):
        request_id=[None];pairing=[None];calls=[]
        def transport(method,path,headers,payload):
            calls.append(path)
            if path=='/api/v1/pairings':
                from speedtester_protocol.crypto import verify
                request=PairingRequest.model_validate(verify(payload,self.possession.public_key(),'pairing-request-v1'));request_id[0]=request.request_id
                pairing[0]=Pairing(request_id=request.request_id,device_code=secrets.token_urlsafe(32),user_code='ABCDE-F2345',verification_uri=self.origin+'/pair',expires_at=int(time.time())+600,interval=5,nonce=secrets.token_urlsafe(32),possession_key=request.possession_key)
                return 201,{},sign(pairing[0].model_dump(),self.server,'pairing-v1')
            check_dpop(headers['DPoP'],self.possession.public_key(),method,self.origin+path,pairing[0].device_code,pairing[0].nonce)
            return 200,{},sign(self.bundle(request_id[0]).model_dump(),self.server,'credentials-v1')
        credentials=Credentials(self.origin,self.possession,self.server.public_key(),self.queue,transport=transport)
        consumer=PairingClient(credentials,self.measurement);pair=consumer.begin()
        self.assertEqual(consumer.begin(),pair);self.assertEqual(calls,['/api/v1/pairings'])
        result=consumer.poll(pair);self.assertEqual(result.request_id,request_id[0])
        self.assertNotIn(result.access_token.encode(),self.queue.path.read_bytes())
        self.assertNotIn(result.refresh_token.encode(),self.queue.path.read_bytes())
        with self.assertRaises(Exception):PairingApproval(user_code=pair.user_code,possession_fingerprint=digest(credentials.identity),confirm=1)

    def test_renewal_preserves_pending_request_on_network_failure_and_restart(self):
        credentials=Credentials(self.origin,self.possession,self.server.public_key(),self.queue,transport=lambda *args:(_ for _ in ()).throw(OSError('offline')))
        old=self.bundle(str(uuid4()));credentials.accept(sign(old.model_dump(),self.server,'credentials-v1'),old.request_id)
        with self.assertRaises(OSError):credentials.ensure_current(force=True)
        pending=self.queue.state(credentials.scope+':rotation');self.assertIsNotNone(pending)
        fresh=self.bundle(pending['request_id']).model_copy(update={'client_id':old.client_id})
        def transport(method,path,headers,payload):
            self.assertEqual(payload['request_id'],pending['request_id'])
            check_dpop(headers['DPoP'],self.possession.public_key(),method,self.origin+path,old.refresh_token,old.nonce)
            return 200,{},sign(fresh.model_dump(),self.server,'credentials-v1')
        restored=Credentials(self.origin,self.possession,self.server.public_key(),self.queue,transport=transport)
        restored.ensure_current();self.assertEqual(restored.bundle,fresh)
        self.assertIsNone(self.queue.state(credentials.scope+':rotation'))

    def test_wrong_credential_identity_request_signature_and_time_are_refused(self):
        credentials=Credentials(self.origin,self.possession,self.server.public_key(),self.queue)
        request=str(uuid4());bundle=self.bundle(request)
        variants=[bundle.model_copy(update={'possession_key':b64(public_bytes(self.measurement))}),bundle.model_copy(update={'request_id':str(uuid4())}),bundle.model_copy(update={'expires_at':1})]
        for item in variants:
            with self.assertRaises(ProtocolError):credentials.accept(sign(item.model_dump(),self.server,'credentials-v1'),request)
        with self.assertRaises(ProtocolError):credentials.accept(sign(bundle.model_dump(),self.measurement,'credentials-v1'),request)
        self.assertIsNone(credentials.bundle)

    def test_discovery_is_https_and_origin_bound(self):
        good={'protocol_version':'1','origin':self.origin,'signing_key':b64(public_bytes(self.server))}
        self.assertEqual(discover(self.origin,lambda *args:(200,{},good)).public_bytes_raw(),self.server.public_key().public_bytes_raw())
        for body in ({**good,'origin':'https://other.example'},{**good,'protocol_version':'2'},{**good,'signing_key':'bad'}):
            with self.assertRaises(ProtocolError):discover(self.origin,lambda *args:(200,{},body))
        with self.assertRaises(ValueError):discover('http://server.example')

    def test_state_permissions_symlinks_corruption_and_exclusive_process(self):
        self.assertEqual(os.stat(self.queue.directory).st_mode&0o777,0o700)
        self.assertEqual(os.stat(self.queue.directory/'storage.key').st_mode&0o777,0o600)
        with exclusive(self.queue):
            with self.assertRaises(ProtocolError):
                with exclusive(self.queue):pass
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['status','--state',str(self.queue.directory)]),1)
        alias=self.directory/'alias';alias.symlink_to(self.queue.directory)
        with self.assertRaises(ValueError):protected_queue(alias)
        os.chmod(self.queue.directory/'storage.key',0o644)
        with self.assertRaises(ValueError):protected_queue(self.queue.directory)
        os.chmod(self.queue.directory/'storage.key',0o600)
        (self.queue.directory/'storage.key').write_bytes(b'invalid')
        with self.assertRaises(ValueError):protected_queue(self.queue.directory)

    def test_service_has_least_privileges_no_tokens_and_safe_quoting(self):
        unit=systemd_unit(self.directory/'space executable',self.directory/'state%name')
        self.assertIn('NoNewPrivileges=true',unit);self.assertIn('UMask=0077',unit)
        self.assertIn('ProtectSystem=strict',unit);self.assertIn('%%name',unit)
        self.assertNotIn('Authorization',unit);self.assertNotIn('User=root',unit)
        with self.assertRaises(ValueError):systemd_unit('/tmp/executable\nExecStart=bad',self.directory)
        root=Path(__file__).resolve().parents[1]
        subprocess.run(['bash','-n',str(root/'install-community.sh')],check=True)

    def grant(self,**updates):
        values=dict(attempt_id=str(uuid4()),client_id=str(uuid4()),profile_digest='a'*64,legal_digest='b'*64,runner='iperf3',target_id='participant-configured',target_scope='unconfirmed',nonce=secrets.token_urlsafe(32),issued_at=int(time.time()),start_before=int(time.time())+120,submit_before=int(time.time())+86400,max_duration_ms=10000,max_bytes=8192)
        values.update(updates);return Grant(**values)

    def executable(self,content):
        file=self.directory/'synthetic-iperf';file.write_text('#!'+sys.executable+'\n'+content);file.chmod(0o700);return str(file)

    def test_actual_runner_process_enforces_grant_payload_commands_and_missing_metrics(self):
        code="""import json,sys
assert '--time' not in sys.argv and '--omit' not in sys.argv
assert sys.argv[sys.argv.index('--parallel')+1]=='1'
assert sys.argv[sys.argv.index('--bytes')+1]=='4096'
end={'sum_sent':{'bits_per_second':10000000,'bytes':4096,'retransmits':2},'sum_received':{'bits_per_second':20000000,'bytes':4096}}
print(json.dumps({'end':end}))
"""
        result=IperfRunner('target.example',binary=self.executable(code))(self.grant())
        self.assertEqual(result.upload_mbps,10);self.assertEqual(result.download_mbps,20)
        self.assertEqual(result.transfer_bytes,8192);self.assertIsNone(result.jitter_ms)
        self.assertIsNone(result.tcp_retransmits)

    def test_runner_deadline_output_limits_payload_overrun_and_target_policy(self):
        runner=IperfRunner('target.example',binary=self.executable('import time;time.sleep(2)'))
        with self.assertRaises(subprocess.TimeoutExpired):runner(self.grant(max_duration_ms=1000))
        oversized=self.executable("print('x'*70000)")
        with self.assertRaises(RuntimeError):IperfRunner('target.example',binary=oversized)(self.grant())
        overrun=self.executable("import json;print(json.dumps({'end':{'sum_sent':{'bits_per_second':10,'bytes':999999}}}))")
        with self.assertRaises(RuntimeError):IperfRunner('target.example',binary=overrun)(self.grant())
        with self.assertRaises(ValueError):runner(self.grant(target_id='another-target'))
        with self.assertRaises(ValueError):IperfRunner('-invalid')


if __name__=='__main__':unittest.main()
