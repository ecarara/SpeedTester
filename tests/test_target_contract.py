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
from speedtester_protocol.targets import TargetRequest, TestTarget, obtain_target, automatic_runner, target_identifier
from speedtester_protocol.runner import IperfRunner
from speedtester_protocol.cli import installation_config


class TargetContractTests(unittest.TestCase):
    def setUp(self):
        self.server=Ed25519PrivateKey.generate();self.client_id=str(uuid4());self.modifier=lambda p:p
        self.signed_modifier=lambda e:e;self.calls=[];self.failure=None
        def transport(method,path,headers,body):
            self.calls.append(path)
            if self.failure:return self.failure
            now=int(time.time())
            payload={'request_id':body['request_id'],'client_id':self.client_id,'runner':'iperf3',
                'target_id':target_identifier('authorized.example',5201,'unconfirmed'),'target_scope':'unconfirmed',
                'host':'authorized.example','port':5201,'issued_at':now,'expires_at':now+300,'protocol_version':'1'}
            return 200,{},self.signed_modifier(sign(self.modifier(payload),self.server,'test-target-v1'))
        self.client=ServerClient('https://server.example','t'*40,Ed25519PrivateKey.generate(),self.server.public_key(),transport=transport)

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

    def test_terminal_setup_prompts_for_profile_and_schedule_only(self):
        queue=Mock();queue.state.side_effect=[None,None]
        answers=iter(['Synthetic provider','ZZ','Test region','Test city','1','1','24'])
        prompts=[]
        def input_fn(prompt):prompts.append(prompt);return next(answers)
        config=installation_config(queue,'https://server.example',self.server.public_key(),input_fn)
        self.assertEqual(config['target_mode'],'automatic')
        self.assertNotIn('host',config);self.assertNotIn('port',config)
        self.assertEqual(len(prompts),7)

    def test_published_automatic_target_schemas_match_consumer(self):
        root=Path(__file__).resolve().parents[1]/'contracts/server-v1'
        for model in (TargetRequest,TestTarget):
            self.assertEqual(json.loads((root/(model.__name__+'.schema.json')).read_text()),model.model_json_schema())
