# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Automatic target policy: signed binding and zero processes/network probes."""
import json
from pathlib import Path
import time
import unittest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import Mock, patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from speedtester_protocol.client import ServerClient, ProtocolError
from speedtester_protocol.crypto import sign
from speedtester_protocol.targets import TargetRequest, TestTarget, TargetAccess, obtain_target, obtain_access, automatic_runner, target_identifier
from speedtester_protocol.runner import IperfRunner
from speedtester_protocol.cli import installation_config
from speedtester_protocol.models import Profile


class TargetContractTests(unittest.TestCase):
    def setUp(self):
        self.server=Ed25519PrivateKey.generate();self.client_id=str(uuid4());self.modifier=lambda p:p
        self.signed_modifier=lambda e:e;self.calls=[];self.bodies=[];self.failure=None
        def transport(method,path,headers,body):
            self.calls.append(path)
            self.bodies.append(body)
            if self.failure:return self.failure
            now=int(time.time())
            payload={'request_id':body['request_id'],'client_id':self.client_id,'runner':'iperf3',
                'target_id':target_identifier('authorized.example',5201,'unconfirmed'),'target_scope':'unconfirmed',
                'host':'authorized.example','port':5201,'issued_at':now,'expires_at':now+300,'protocol_version':'1'}
            return 200,{},self.signed_modifier(sign(self.modifier(payload),self.server,'test-target-v1'))
        self.client=ServerClient('https://server.example','t'*40,Ed25519PrivateKey.generate(),self.server.public_key(),transport=transport)

    def test_location_profile_is_sent_only_to_the_server_policy_endpoint(self):
        profile=Profile(version=1,operator='Synthetic',country_code='BR',region='SP',city='São Paulo',access_type='fiber',link_type='ethernet')
        obtain_target(self.client,self.client_id,profile)
        self.assertEqual(self.calls,['/api/v1/test-target'])
        self.assertEqual(self.bodies[0]['profile'],profile.model_dump())

    def test_signed_target_is_bound_to_this_client_request_endpoint_and_short_lifetime(self):
        target=obtain_target(self.client,self.client_id)
        self.assertEqual(target.host,'authorized.example')
        self.assertEqual(target.target_scope,'unconfirmed')
        self.assertEqual(self.calls,['/api/v1/test-target'])
        self.assertEqual(target.expires_at-target.issued_at,300)

    def test_signature_mutation_wrong_context_expiry_and_endpoint_changes_are_rejected(self):
        cases=[{'client_id':str(uuid4())},{'request_id':str(uuid4())},{'host':'modified.example'},
               {'port':5202},{'target_scope':'external-controlled'},{'expires_at':1},{'expires_at':int(time.time())+3600},
               {'issued_at':int(time.time())+100},{'host':'--help'},{'host':'https://example.com'}]
        for changes in cases:
            with self.subTest(changes=changes):
                self.modifier=lambda payload:{**payload,**changes}
                with self.assertRaisesRegex(ProtocolError,'invalid_test_target'):obtain_target(self.client,self.client_id)
        self.modifier=lambda payload:payload
        def corrupt(envelope):envelope['payload']['port']=5202;return envelope
        self.signed_modifier=corrupt
        with self.assertRaisesRegex(ProtocolError,'invalid_test_target'):obtain_target(self.client,self.client_id)

    def test_unavailable_or_revoked_policy_never_falls_back_to_a_local_target(self):
        for code in ('test_target_unavailable','client_revoked','account_disabled','terms_acceptance_required'):
            self.failure=(403,{}, {'code':code})
            with self.assertRaisesRegex(ProtocolError,code):obtain_target(self.client,self.client_id)

    def test_runner_refuses_mismatched_grant_or_expired_target_before_execution(self):
        execute=Mock()
        runner=automatic_runner(self.client,self.client_id,execute)
        grant=SimpleNamespace(runner='iperf3',target_id=target_identifier('authorized.example',5201,'unconfirmed'),target_scope='unconfirmed',max_bytes=4096,max_duration_ms=1000)
        for field,value in [('target_id','participant-configured'),('target_scope','lan')]:
            with self.subTest(field=field):
                other=SimpleNamespace(**{**vars(grant),field:value})
                with self.assertRaisesRegex(ProtocolError,"test_target_changed"):runner(other)
        bound=IperfRunner('authorized.example',target_id=grant.target_id,target_scope='unconfirmed',expires_at=1)
        with patch('speedtester_protocol.runner.subprocess.Popen') as process:
            with self.assertRaises(ValueError):bound(grant)
            process.assert_not_called()
        execute.assert_not_called()

    def test_terminal_setup_prompts_for_profile_without_manual_schedule(self):
        queue=Mock();queue.state.side_effect=[None,None]
        answers=iter(['Synthetic provider','ZZ','Test region','Test city','1','1'])
        prompts=[]
        def input_fn(prompt):prompts.append(prompt);return next(answers)
        config=installation_config(queue,'https://server.example',self.server.public_key(),input_fn)
        self.assertEqual(config['target_mode'],'automatic')
        self.assertNotIn('host',config);self.assertNotIn('port',config)
        self.assertEqual(len(prompts),6)
        self.assertEqual(config["schedule"]["format"],"quadrants-v1")
        self.assertNotIn("interval",config)

    def test_published_automatic_target_schemas_match_consumer(self):
        root=Path(__file__).resolve().parents[1]/'contracts/server-v1'
        for model in (TargetRequest,TestTarget,TargetAccess):
            self.assertEqual(json.loads((root/(model.__name__+'.schema.json')).read_text()),model.model_json_schema())


class TargetAccessTests(unittest.TestCase):
    def test_one_use_access_binding_mutation_expiry_and_no_plaintext_repr(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
        key=Ed25519PrivateKey.generate();attempt=str(uuid4());identity=str(uuid4())
        target=SimpleNamespace(host='target.example',target_id=target_identifier('target.example',5201,'external-controlled','rsa-ephemeral-v1'))
        grant=SimpleNamespace(attempt_id=attempt,client_id=identity,target_id=target.target_id)
        pem=rsa.generate_private_key(public_exponent=65537,key_size=2048).public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo).decode()
        changes={}
        def transport(method,path,headers,body):
            self.assertEqual(path,'/api/v1/attempts/'+attempt+'/target-access')
            payload=dict(request_id=body['request_id'],attempt_id=attempt,client_id=identity,target_id=target.target_id,
                host=target.host,upload_port=5201,download_port=5202,username=attempt,password='secret-value-should-not-appear-123456',rsa_public_key=pem,expires_at=int(time.time())+30)
            payload.update(changes)
            return 200,{},sign(payload,key,'target-access-v1')
        client=ServerClient('https://server.example','t'*40,Ed25519PrivateKey.generate(),key.public_key(),transport=transport)
        access=obtain_access(client,target,grant)
        self.assertNotIn(access.password,repr(access))
        for values in ({'attempt_id':str(uuid4())},{'client_id':str(uuid4())},{'request_id':str(uuid4())},
                {'host':'another.example'},{'target_id':target_identifier('another.example',5201,'lan')},
                {'download_port':5201},{'username':str(uuid4())},{'expires_at':1},{'expires_at':int(time.time())+60},{'rsa_public_key':'invalid'*50}):
            with self.subTest(values=values):
                changes.clear();changes.update(values)
                with self.assertRaisesRegex(ProtocolError,'invalid_target_access'):obtain_access(client,target,grant)

    def test_authentication_secret_never_enters_arguments_and_uses_bundled_paths(self):
        import tempfile
        access=SimpleNamespace(upload_port=5201,download_port=5202,username=str(uuid4()),password='never-log-this-secret',rsa_public_key='public-fixture',expires_at=int(time.time())+30)
        grant=SimpleNamespace(runner='iperf3',target_id='secured',target_scope='external-controlled',max_bytes=8192,max_duration_ms=30000)
        commands=[]
        def capture(command,deadline,maximum,environment):
            commands.append(command)
            self.assertNotIn(access.password,' '.join(command))
            self.assertEqual(environment['IPERF3_PASSWORD'],access.password)
            self.assertEqual(Path(command[command.index('--rsa-public-key-path')+1]).read_text(),access.rsa_public_key)
            return json.dumps({'end':{'sum_received':{'bytes':4096,'bits_per_second':1000000},'sum_sent':{'bytes':4096,'bits_per_second':2000000}}}).encode()
        runner=IperfRunner('target.example',binary='/bundled/tools/iperf3',target_id='secured',target_scope='external-controlled',authorize=lambda g:access)
        with patch.object(runner,'_capture',side_effect=capture):self.assertEqual(runner(grant).transfer_bytes,8192)
        self.assertEqual([c[c.index('--port')+1] for c in commands],['5201','5202'])
        self.assertEqual(len(commands),2)

    def test_frozen_tool_does_not_fall_back_to_workstation_path(self):
        import tempfile
        from speedtester_protocol.bundled_tools import iperf_binary
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'tools').mkdir()
            with patch('speedtester_protocol.bundled_tools.sys.frozen',True,create=True),patch('speedtester_protocol.bundled_tools.sys.executable',str(root/'client')),patch('speedtester_protocol.bundled_tools.shutil.which') as path:
                self.assertIsNone(iperf_binary())
                name='iperf3.exe' if __import__('sys').platform=='win32' else 'iperf3'
                tool=root/'tools'/name;tool.write_text('fixture')
                self.assertEqual(iperf_binary(),str(tool));path.assert_not_called()
