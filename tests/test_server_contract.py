# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Public consumer tests exercise real crypto and transport code, not private sources."""
import json,secrets,tempfile,time,unittest
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from speedtester_protocol.crypto import canonical,digest,sign,verify,make_dpop,check_dpop,public_bytes
from speedtester_protocol.models import Profile,Observation,Manifest,Grant,Receipt,Acceptance,METRICS
from speedtester_protocol.client import ServerClient,HTTPS,ProtocolError
from speedtester_protocol.queue import EncryptedQueue


def profile():
    return Profile(version=1,operator="Synthetic operator",country_code="ZZ",region="Test region",city="Test city",access_type="fiber",link_type="ethernet")


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.device,self.server=Ed25519PrivateKey.generate(),Ed25519PrivateKey.generate()
        self.attempt=str(uuid4());self.nonce=secrets.token_urlsafe(32)

    def observation(self,**changes):
        payload=dict(observation_id=str(uuid4()),attempt_id=self.attempt,metric="jitter",unit="us",value=2500,status="valid",method="icmp:rtt-samples",measured_at=int(time.time()),profile_digest=digest(profile().model_dump()),legal_digest="a"*64,nonce=self.nonce)
        payload.update(changes)
        return payload

    def test_metric_units_ranges_missing_values_and_unknown_fields(self):
        for changes in ({"unit":"ms"},{"value":-1},{"value":float("nan")},{"value":True},{"value":None},{"status":"not-supported"},{"public_ip":"192.0.2.9"},{"protocol_version":"2"}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ValidationError):Observation.model_validate(self.observation(**changes))
        self.assertIsNone(Observation.model_validate(self.observation(value=None,status="not-supported")).value)
        with self.assertRaises(ValidationError):profile().model_copy().model_validate({**profile().model_dump(),"link_type":"unknown"})
        with self.assertRaises(ValidationError):Manifest(attempt_id=self.attempt,nonce=self.nonce,profile_digest="a"*64,legal_digest="a"*64,observations={"jitter":"a"*64})

    def test_canonical_hash_signature_detect_mutation_wrong_key_and_domain(self):
        payload=Observation.model_validate(self.observation()).model_dump()
        envelope=sign(payload,self.device,"observation-v1")
        self.assertEqual(verify(envelope,self.device.public_key(),"observation-v1"),payload)
        self.assertEqual(digest({"b":2,"a":1}),digest({"a":1,"b":2}))
        with self.assertRaises(Exception):verify(envelope,self.server.public_key(),"observation-v1")
        with self.assertRaises(Exception):verify(envelope,self.device.public_key(),"manifest-v1")
        envelope["payload"]["value"]+=1
        with self.assertRaises(Exception):verify(envelope,self.device.public_key(),"observation-v1")

    def test_dpop_binding_and_replay_identifier_are_real_signed_values(self):
        token=secrets.token_urlsafe(32);uri="https://server.example/api/v1/metric-observations";now=int(time.time())
        proof=make_dpop(self.device,"POST",uri,token,self.nonce,now=now)
        first=check_dpop(proof,self.device.public_key(),"POST",uri,token,self.nonce,now=now)
        second=check_dpop(make_dpop(self.device,"POST",uri,token,self.nonce,now=now),self.device.public_key(),"POST",uri,token,self.nonce,now=now)
        self.assertNotEqual(first,second)
        for key,method,url,credential,nonce,timestamp in ((self.server.public_key(),"POST",uri,token,self.nonce,now),(self.device.public_key(),"GET",uri,token,self.nonce,now),(self.device.public_key(),"POST",uri+"/other",token,self.nonce,now),(self.device.public_key(),"POST",uri,token+"x",self.nonce,now),(self.device.public_key(),"POST",uri,token,self.nonce,now+31)):
            with self.assertRaises(Exception):check_dpop(proof,key,method,url,credential,nonce,now=timestamp)

    def test_real_consumer_sends_proof_and_refuses_wrong_or_unsigned_receipt(self):
        payload=Observation.model_validate(self.observation()).model_dump();envelope=sign(payload,self.device,"observation-v1");calls=[]
        token=secrets.token_urlsafe(32)
        def transport(method,path,headers,data):
            calls.append(headers)
            self.assertNotIn(token,path);self.assertEqual(headers["Authorization"],"DPoP "+token)
            if len(calls)==1:return 401,{"DPoP-Nonce":self.nonce},{"code":"use_dpop_nonce"}
            check_dpop(headers["DPoP"],self.device.public_key(),method,"https://server.example"+path,token,self.nonce)
            receipt=Receipt(attempt_id=self.attempt,observation_id=payload["observation_id"],kind="observation",digest=digest(payload),accepted_at=int(time.time()))
            return 200,{},sign(receipt.model_dump(),self.server,"receipt-v1")
        client=ServerClient("https://server.example",token,self.device,self.server.public_key(),transport=transport)
        self.assertEqual(client.observation(envelope)["payload"]["digest"],digest(payload));self.assertEqual(len(calls),2)
        bad=Receipt(attempt_id=self.attempt,observation_id=payload["observation_id"],kind="observation",digest="b"*64,accepted_at=int(time.time()))
        with self.assertRaises(ProtocolError):client.receipt(sign(bad.model_dump(),self.server,"receipt-v1"),"observation",self.attempt,digest(payload),payload["observation_id"])
        with self.assertRaises(ProtocolError):client.receipt({"payload":payload},"observation",self.attempt,digest(payload))

    def test_published_schemas_match_consumer_models(self):
        from speedtester_protocol import models
        root=Path(__file__).resolve().parents[1]/"contracts/server-v1"
        for name in ("Profile","GrantRequest","Grant","Observation","Manifest","Envelope","Receipt","Enrollment","Acceptance","PairingRequest","Pairing","CredentialBundle","RotationRequest","PairingApproval"):
            self.assertEqual(json.loads((root/(name+".schema.json")).read_text()),getattr(models,name).model_json_schema())

    def test_https_origin_and_no_redirect_contract(self):
        for url in ("http://server.example","https://secret@server.example","https://server.example/path","https://server.example?token=hidden"):
            with self.assertRaises(ValueError):HTTPS(url)
        self.assertEqual(HTTPS("https://server.example/").origin,"https://server.example")

    def test_encrypted_queue_atomic_conflict_corruption_and_destination_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            key=secrets.token_bytes(32);queue=EncryptedQueue(directory,key)
            first={"id":str(uuid4()),"kind":"observation","operator":"PRIVATE_OPERATOR","value":912345678}
            queue.put(first,"destination-a")
            self.assertNotIn(b"PRIVATE_OPERATOR",queue.path.read_bytes())
            self.assertNotIn(b"912345678",queue.path.read_bytes())
            reopened=EncryptedQueue(directory,key);self.assertEqual(reopened.pending("destination-a"),[first])
            new={"id":str(uuid4()),"kind":"manifest"}
            with self.assertRaises(ValueError):queue.put_batch([new,{**first,"value":1}],"destination-a")
            self.assertEqual(len(queue.pending("destination-a")),1)
            with queue.connection() as conn:conn.execute("UPDATE entries SET destination='destination-b'")
            with self.assertRaises(Exception):queue.pending("destination-b")
            with self.assertRaises(Exception):EncryptedQueue(directory,secrets.token_bytes(32)).pending("destination-b")


    def agent_fixture(self):
        from speedtester_protocol.agent import CommunityAgent
        from types import SimpleNamespace
        measurement=Ed25519PrivateKey.generate();state={"observations":[],"grants":{},"starts":0}
        token=secrets.token_urlsafe(32)
        def transport(method,path,headers,payload):
            if "DPoP" not in headers:return 401,{"DPoP-Nonce":self.nonce},{"code":"use_dpop_nonce"}
            check_dpop(headers["DPoP"],self.device.public_key(),method,"https://server.example"+path,token,self.nonce)
            if path=="/api/v1/measurement-grants":
                if payload["request_id"] not in state["grants"]:
                    grant=Grant(attempt_id=str(uuid4()),client_id=str(uuid4()),profile_digest=digest(payload["profile"]),legal_digest="a"*64,runner=payload["runner"],target_id="synthetic-target",target_scope="unconfirmed",nonce=self.nonce,issued_at=int(time.time()),start_before=int(time.time())+120,submit_before=int(time.time())+86400,max_duration_ms=30000,max_bytes=100000000)
                    state["grants"][payload["request_id"]]=grant
                state["grant"]=state["grants"][payload["request_id"]]
                return 200,{},sign(state["grant"].model_dump(),self.server,"grant-v1")
            if path.endswith("/start"):
                state["starts"]+=1
                receipt=Receipt(attempt_id=state["grant"].attempt_id,kind="started",digest=digest(state["grant"].model_dump()),accepted_at=int(time.time()))
            elif path=="/api/v1/metric-observations":
                observation=Observation.model_validate(verify(payload,measurement.public_key(),"observation-v1"));state["observations"].append(observation)
                receipt=Receipt(attempt_id=observation.attempt_id,observation_id=observation.observation_id,kind="observation",digest=digest(observation.model_dump()),accepted_at=int(time.time()))
            else:
                manifest=Manifest.model_validate(verify(payload,measurement.public_key(),"manifest-v1"))
                self.assertEqual(set(manifest.observations),set(METRICS))
                receipt=Receipt(attempt_id=manifest.attempt_id,kind="manifest",digest=digest(manifest.model_dump()),accepted_at=int(time.time()))
            return 200,{},sign(receipt.model_dump(),self.server,"receipt-v1")
        client=ServerClient("https://server.example",token,self.device,self.server.public_key(),transport=transport)
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        queue=EncryptedQueue(directory.name,secrets.token_bytes(32))
        agent=CommunityAgent(client,queue,measurement,profile(),"iperf3")
        result=SimpleNamespace(download_mbps=100,upload_mbps=50,ping_ms=2,jitter_ms=None,packet_loss_pct=None,duration_sec=1,transfer_bytes=1000,tcp_retransmits=0)
        return agent,result,state

    def test_agent_obtains_grant_before_runner_and_preserves_missing_metrics(self):
        agent,result,state=self.agent_fixture()
        def execute(grant):
            self.assertEqual(state["starts"],1)
            return result
        agent.run_once(execute)
        metrics={record.metric:record for record in state["observations"]}
        self.assertEqual(metrics["download"].value,100000000)
        self.assertIsNone(metrics["jitter"].value);self.assertEqual(metrics["jitter"].status,"not-supported")
        self.assertEqual(agent.queue.pending(agent.destination),[])
        self.assertIsNotNone(agent.state("previous_receipt"))

    def test_agent_no_valid_grant_means_no_runner_execution(self):
        agent,result,state=self.agent_fixture();calls=[]
        agent.client.transport=lambda *args:(403,{}, {"code":"terms_acceptance_required"})
        with self.assertRaises(ProtocolError):agent.run_once(lambda grant:calls.append(grant))
        self.assertEqual(calls,[])

    def test_agent_restores_interrupted_attempt_as_error_without_repeating_test(self):
        agent,result,state=self.agent_fixture()
        def interrupted(grant):raise SystemExit()
        with self.assertRaises(SystemExit):agent.run_once(interrupted)
        agent.run_once(lambda grant:self.fail("A started grant must not run twice"))
        self.assertEqual(len(state["grants"]),1)
        self.assertEqual({record.status for record in state["observations"]},{"error"})
        self.assertIsNone(agent.state("active_attempt"))


    def test_queue_state_does_not_cross_server_or_installation_identity(self):
        from speedtester_protocol.agent import CommunityAgent
        agent,result,state=self.agent_fixture();agent.state("active_attempt",{"synthetic":"first-installation"})
        other=ServerClient(agent.client.origin,secrets.token_urlsafe(32),Ed25519PrivateKey.generate(),self.server.public_key(),transport=agent.client.transport)
        second=CommunityAgent(other,agent.queue,agent.key,profile(),"iperf3")
        self.assertIsNone(second.state("active_attempt"));self.assertNotEqual(second.destination,agent.destination)
        self.assertEqual(agent.state("active_attempt"),{"synthetic":"first-installation"})

if __name__=="__main__":unittest.main()
