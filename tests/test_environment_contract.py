# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Consumer contract for minimal OS reporting; no network or measurement runner."""
import secrets,tempfile,time,unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from speedtester_protocol.crypto import b64,public_bytes,digest,sign,verify,check_dpop
from speedtester_protocol.models import CredentialBundle,EnvironmentReport,EnvironmentReceipt,SystemEnvironment
from speedtester_protocol.enrollment import Credentials
from speedtester_protocol.installation import protected_queue
from speedtester_protocol.environment import collect_environment,sync_environment
from speedtester_protocol.client import ProtocolError

class EnvironmentContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.queue=protected_queue(Path(self.temp.name).resolve()/'state')
        self.possession,self.measurement,self.server=(Ed25519PrivateKey.generate() for _ in range(3))
        self.origin='https://server.example';self.calls=[];self.reject=False;self.tamper=False
        self.bundle=CredentialBundle(client_id=str(uuid4()),access_token=secrets.token_urlsafe(32),refresh_token=secrets.token_urlsafe(32),expires_at=int(time.time())+900,refresh_expires_at=int(time.time())+86400,nonce=secrets.token_urlsafe(32),possession_key=b64(public_bytes(self.possession)),request_id=str(uuid4()))
        self.credentials=Credentials(self.origin,self.possession,self.server.public_key(),self.queue,transport=self.transport)

    def transport(self,method,path,headers,payload):
        self.calls.append(path)
        if path=='/.well-known/speedtester-server':
            return 200,{},dict(protocol_version='1',origin=self.origin,signing_key=b64(public_bytes(self.server)),capabilities=['client-environment-v1'])
        self.assertEqual(path,'/api/v1/client-environment')
        self.assertEqual(headers['Authorization'],'DPoP '+self.bundle.access_token)
        check_dpop(headers['DPoP'],self.possession.public_key(),method,self.origin+path,self.bundle.access_token,self.bundle.nonce)
        report=EnvironmentReport.model_validate(verify(payload,self.measurement.public_key(),'client-environment-v1'))
        if self.reject:return 403,{}, {'code':'account_disabled'}
        receipt=EnvironmentReceipt(environment_id=report.environment_id,client_id=str(uuid4()) if self.tamper else report.client_id,digest=digest(report.model_dump()),accepted_at=int(time.time()))
        return 200,{},sign(receipt.model_dump(),self.server,'environment-receipt-v1')

    def pair(self):self.credentials.accept(sign(self.bundle.model_dump(),self.server,'credentials-v1'),self.bundle.request_id)

    def test_only_allowlisted_os_fields_are_collected_and_malformed_release_is_omitted(self):
        release={'ID':'test-linux','VERSION_ID':'44','PRETTY_NAME':'PRIVATE HOST','HOME_URL':'https://private.example','HOSTNAME':'PRIVATE HOST'}
        with patch('platform.system',return_value='Linux'),patch('platform.machine',return_value='x86_64'),patch('platform.freedesktop_os_release',return_value=release):
            self.assertEqual(collect_environment().model_dump(),dict(system='linux',distribution='test-linux',version='44',architecture='amd64'))
        release={'ID':'contains spaces','VERSION_ID':'hostname\nsecret'}
        with patch('platform.system',return_value='Linux'),patch('platform.freedesktop_os_release',return_value=release):
            value=collect_environment();self.assertIsNone(value.distribution);self.assertIsNone(value.version)
        with self.assertRaises(ValidationError):SystemEnvironment(system='linux',architecture='amd64',hostname='PRIVATE')

    def test_unpaired_client_never_collects_or_sends_os_metadata(self):
        with patch('speedtester_protocol.environment.collect_environment') as collect:
            with self.assertRaises(ProtocolError):sync_environment(self.credentials,self.measurement)
            collect.assert_not_called()
        self.assertEqual(self.calls,[])

    def test_authenticated_signed_report_is_deduplicated_and_stored_only_encrypted(self):
        self.pair();environment=SystemEnvironment(system='linux',distribution='test-private-distro',version='44',architecture='amd64')
        with patch('speedtester_protocol.environment.collect_environment',return_value=environment):
            self.assertTrue(sync_environment(self.credentials,self.measurement))
            self.assertFalse(sync_environment(self.credentials,self.measurement))
        self.assertEqual(self.calls.count('/api/v1/client-environment'),1)
        self.assertNotIn(b'test-private-distro',self.queue.path.read_bytes())

    def test_rejection_or_wrong_receipt_keeps_same_pending_report_for_retry(self):
        self.pair();self.reject=True
        with self.assertRaises(ProtocolError):sync_environment(self.credentials,self.measurement)
        scope=self.credentials.scope+':environment';pending=self.queue.state(scope+':pending')
        self.reject=False;self.tamper=True
        with self.assertRaises(ProtocolError):sync_environment(self.credentials,self.measurement)
        self.assertEqual(self.queue.state(scope+':pending'),pending)
        self.tamper=False;self.assertTrue(sync_environment(self.credentials,self.measurement))
        self.assertIsNone(self.queue.state(scope+':pending'))

if __name__=='__main__':unittest.main()
