# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Public consumer tests exercise real crypto and transport code, not private sources."""
import json,secrets,tempfile,time,unittest
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError
from cryptography.exceptions import InvalidSignature
from nacl.exceptions import CryptoError, TypeError as InvalidNonce
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
                payload=self.observation(**changes)
                with self.assertRaises(ValidationError):Observation.model_validate(payload)
        self.assertIsNone(Observation.model_validate(self.observation(value=None,status="not-supported")).value)
        invalid_profile={**profile().model_dump(),"link_type":"unknown"}
        with self.assertRaises(ValidationError):Profile.model_validate(invalid_profile)
        with self.assertRaises(ValidationError):Manifest(attempt_id=self.attempt,nonce=self.nonce,profile_digest="a"*64,legal_digest="a"*64,observations={"jitter":"a"*64})

    def test_canonical_hash_signature_detect_mutation_wrong_key_and_domain(self):
        payload=Observation.model_validate(self.observation()).model_dump()
        envelope=sign(payload,self.device,"observation-v1")
        self.assertEqual(verify(envelope,self.device.public_key(),"observation-v1"),payload)
        self.assertEqual(digest({"b":2,"a":1}),digest({"a":1,"b":2}))
        wrong_key=self.server.public_key();correct_key=self.device.public_key()
        with self.assertRaisesRegex(ValueError,"untrusted signing key"):verify(envelope,wrong_key,"observation-v1")
        with self.assertRaises(InvalidSignature):verify(envelope,correct_key,"manifest-v1")
        envelope["payload"]["value"]+=1
        with self.assertRaises(InvalidSignature):verify(envelope,correct_key,"observation-v1")

    def test_dpop_binding_and_replay_identifier_are_real_signed_values(self):
        token=secrets.token_urlsafe(32);uri="https://server.example/api/v1/metric-observations";now=int(time.time())
        proof=make_dpop(self.device,"POST",uri,token,self.nonce,now=now)
        first=check_dpop(proof,self.device.public_key(),"POST",uri,token,self.nonce,now=now)
        second=check_dpop(make_dpop(self.device,"POST",uri,token,self.nonce,now=now),self.device.public_key(),"POST",uri,token,self.nonce,now=now)
        self.assertNotEqual(first,second)
        for key,method,url,credential,nonce,timestamp in ((self.server.public_key(),"POST",uri,token,self.nonce,now),(self.device.public_key(),"GET",uri,token,self.nonce,now),(self.device.public_key(),"POST",uri+"/other",token,self.nonce,now),(self.device.public_key(),"POST",uri,token+"x",self.nonce,now),(self.device.public_key(),"POST",uri,token,self.nonce,now+31)):
            with self.assertRaises(ValueError):check_dpop(proof,key,method,url,credential,nonce,now=timestamp)

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
        bad_envelope=sign(bad.model_dump(),self.server,"receipt-v1");expected_digest=digest(payload)
        with self.assertRaises(ProtocolError):client.receipt(bad_envelope,"observation",self.attempt,expected_digest,payload["observation_id"])
        with self.assertRaises(ProtocolError):client.receipt({"payload":payload},"observation",self.attempt,expected_digest)

    def test_published_schemas_match_consumer_models(self):
        from speedtester_protocol import models
        root=Path(__file__).resolve().parents[1]/"contracts/server-v1"
        for name in ("Profile","GrantRequest","Grant","Observation","Manifest","Envelope","Receipt","Enrollment","Acceptance","PairingRequest","Pairing","CredentialBundle","RotationRequest","PairingApproval","SystemEnvironment","EnvironmentReport","EnvironmentReceipt","ScheduleSlot","MachineReport","MachinePolicy"):
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
            with self.assertRaises(CryptoError):queue.pending("destination-b")
            wrong_queue=EncryptedQueue(directory,secrets.token_bytes(32))
            with self.assertRaises(CryptoError):wrong_queue.pending("destination-b")


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


    def test_manifest_uses_signed_grant_chain_head_instead_of_stale_queue_state(self):
        agent,result,state=self.agent_fixture();transport=agent.client.transport;chain="c"*64;manifests=[]
        agent.state("previous_receipt","d"*64)
        def recovered_chain(method,path,headers,payload):
            response=transport(method,path,headers,payload)
            if path=="/api/v1/measurement-grants" and response[0]==200:
                grant=state["grant"].model_copy(update={"previous_receipt":chain})
                state["grant"]=grant;state["grants"][payload["request_id"]]=grant
                return 200,{},sign(grant.model_dump(),self.server,"grant-v1")
            if path.endswith("/finalize"):manifests.append(payload["payload"])
            return response
        agent.client.transport=recovered_chain
        agent.run_once(lambda grant:result)
        self.assertEqual(len(manifests),1)
        self.assertEqual(manifests[0]["previous_receipt"],chain)
        self.assertNotEqual(agent.state("previous_receipt"),chain)

    def test_expired_grant_request_recovers_once_without_executing_old_grant(self):
        agent,result,state=self.agent_fixture();transport=agent.client.transport;expired=[None];executed=[]
        def lose_window(method,path,headers,payload):
            response=transport(method,path,headers,payload)
            if path=="/api/v1/measurement-grants" and response[0]==200 and expired[0] is None:
                grant=state["grant"].model_copy(update={"start_before":int(time.time())-1})
                state["grants"][payload["request_id"]]=grant;expired[0]=grant
                return 200,{},sign(grant.model_dump(),self.server,"grant-v1")
            return response
        agent.client.transport=lose_window
        agent.run_once(lambda grant:executed.append(grant.attempt_id) or result)
        self.assertEqual(len(state["grants"]),2);self.assertEqual(len(executed),1)
        self.assertNotEqual(executed[0],expired[0].attempt_id)
        evidence=agent.state("quarantine:"+expired[0].attempt_id)
        self.assertEqual(evidence["code"],"grant_expired");self.assertEqual(evidence["grant"],expired[0].model_dump())
        self.assertIsNone(agent.state("active_attempt"))

    def test_expired_active_restart_preserves_evidence_and_never_reexecutes(self):
        agent,result,state=self.agent_fixture()
        with self.assertRaises(SystemExit):agent.run_once(lambda grant:(_ for _ in ()).throw(SystemExit()))
        old=agent.state("active_attempt");transport=agent.client.transport;executed=[]
        def expire_old(method,path,headers,payload):
            if path=="/api/v1/attempts/"+old["attempt_id"]+"/start":return 409,{}, {"code":"start_expired"}
            return transport(method,path,headers,payload)
        agent.client.transport=expire_old
        agent.run_once(lambda grant:executed.append(grant.attempt_id) or result)
        self.assertEqual(len(executed),1);self.assertNotEqual(executed[0],old["attempt_id"])
        self.assertEqual(agent.state("quarantine:"+old["attempt_id"])["grant"],old)
        self.assertIsNone(agent.state("active_attempt"))

    def test_recovery_only_never_creates_another_grant_after_expiration(self):
        agent,result,state=self.agent_fixture()
        with self.assertRaises(SystemExit):agent.run_once(lambda grant:(_ for _ in ()).throw(SystemExit()))
        old=agent.state("active_attempt");transport=agent.client.transport
        def expire_old(method,path,headers,payload):
            if path=="/api/v1/attempts/"+old["attempt_id"]+"/start":return 409,{}, {"code":"start_expired"}
            return transport(method,path,headers,payload)
        agent.client.transport=expire_old
        self.assertIsNone(agent.run_once(lambda grant:self.fail("Recovery must not execute"),allow_new=False))
        self.assertEqual(len(state["grants"]),1)
        self.assertIsNone(agent.state("active_attempt"))
        self.assertEqual(agent.state("quarantine:"+old["attempt_id"])["grant"],old)
        self.assertIsNone(agent.run_once(None,allow_new=False))
        self.assertEqual(len(state["grants"]),1)

    def test_terminal_pending_attempt_is_quarantined_without_false_acceptance(self):
        agent,result,state=self.agent_fixture();transport=agent.client.transport;observations=[0]
        def fail_after_first(method,path,headers,payload):
            if path=="/api/v1/metric-observations":
                observations[0]+=1
                if observations[0]>1:return 503,{}, {"code":"temporarily_unavailable"}
            return transport(method,path,headers,payload)
        agent.client.transport=fail_after_first
        with self.assertRaises(ProtocolError):agent.run_once(lambda grant:result)
        pending=agent.queue.pending(agent.destination);self.assertEqual(len(pending),8)
        old_attempt=pending[0]["envelope"]["payload"]["attempt_id"]
        def expire_old(method,path,headers,payload):
            if payload and payload.get("payload",{}).get("attempt_id")==old_attempt:return 409,{}, {"code":"attempt_expired"}
            return transport(method,path,headers,payload)
        agent.client.transport=expire_old
        new_attempt=agent.run_once(lambda grant:result)
        self.assertNotEqual(new_attempt,old_attempt)
        self.assertEqual(agent.queue.quarantined(agent.destination),pending)
        self.assertEqual(agent.queue.pending(agent.destination),[])
        with agent.queue.connection() as conn:
            statuses=conn.execute("SELECT status,COUNT(*) FROM entries GROUP BY status").fetchall()
            self.assertEqual(dict(statuses),{"accepted":10,"quarantined":8})
            for record in pending:
                self.assertIsNone(conn.execute("SELECT receipt FROM entries WHERE id=?",(record["id"],)).fetchone()[0])
        self.assertEqual(agent.state("quarantine:"+old_attempt)["code"],"attempt_expired")

    def test_authentication_signature_and_consent_errors_leave_queue_pending(self):
        for code in ("client_revoked","terms_acceptance_required","invalid_receipt","invalid_signature","invalid_proof"):
            agent,result,state=self.agent_fixture();transport=agent.client.transport
            def blocked(method,path,headers,payload):
                if path=="/api/v1/metric-observations":return 403,{}, {"code":code}
                return transport(method,path,headers,payload)
            agent.client.transport=blocked
            with self.assertRaises(ProtocolError):agent.run_once(lambda grant:result)
            self.assertEqual(len(agent.queue.pending(agent.destination)),9)
            self.assertEqual(agent.queue.quarantined(agent.destination),[])

    def test_legal_context_request_recovery_is_bounded(self):
        agent,result,state=self.agent_fixture();requests=[]
        def changed(method,path,headers,payload):
            requests.append(payload["request_id"])
            return 409,{}, {"code":"legal_context_changed"}
        agent.client.transport=changed
        with self.assertRaises(ProtocolError) as error:agent.run_once(lambda grant:self.fail("terminal grant must not execute"))
        self.assertEqual(error.exception.code,"terminal_attempt_recovery_pending")
        self.assertEqual(len(requests),2);self.assertNotEqual(requests[0],requests[1])
        self.assertNotIn(agent.state("grant_request"),requests)
        self.assertEqual(agent.state("quarantine:"+requests[0])["request_id"],requests[0])

    def test_quarantine_is_atomic_when_an_encrypted_entry_is_corrupted(self):
        agent,result,state=self.agent_fixture();attempt=str(uuid4());request=str(uuid4())
        agent.state("active_attempt",{"attempt_id":attempt});agent.state("grant_request",request)
        records=[{"id":str(uuid4()),"kind":"observation","envelope":{"payload":{"attempt_id":attempt}}} for _ in range(2)]
        agent.queue.put_batch(records,agent.destination)
        with agent.queue.connection() as conn:conn.execute("UPDATE entries SET ciphertext=? WHERE id=?",(b"corrupted",records[1]["id"]))
        with self.assertRaisesRegex(InvalidNonce,"Nonce must be a 24 bytes long bytes sequence"):agent.queue.quarantine_attempt(agent.destination,attempt,"attempt_expired")
        with agent.queue.connection() as conn:self.assertEqual(conn.execute("SELECT DISTINCT status FROM entries").fetchall(),[("pending",)])
        self.assertEqual(agent.state("active_attempt"),{"attempt_id":attempt})
        self.assertEqual(agent.state("grant_request"),request)
        self.assertIsNone(agent.state("quarantine:"+attempt))

    def test_quarantine_older_attempt_cannot_clear_a_different_live_attempt(self):
        agent,result,state=self.agent_fixture();older=str(uuid4());live=str(uuid4());request=str(uuid4())
        agent.state("active_attempt",{"attempt_id":live});agent.state("grant_request",request)
        agent.queue.quarantine_attempt(agent.destination,older,"attempt_expired")
        self.assertEqual(agent.state("active_attempt"),{"attempt_id":live})
        self.assertEqual(agent.state("grant_request"),request)

    def test_queue_state_does_not_cross_server_or_installation_identity(self):
        from speedtester_protocol.agent import CommunityAgent
        agent,result,state=self.agent_fixture();agent.state("active_attempt",{"synthetic":"first-installation"})
        other=ServerClient(agent.client.origin,secrets.token_urlsafe(32),Ed25519PrivateKey.generate(),self.server.public_key(),transport=agent.client.transport)
        second=CommunityAgent(other,agent.queue,agent.key,profile(),"iperf3")
        self.assertIsNone(second.state("active_attempt"));self.assertNotEqual(second.destination,agent.destination)
        self.assertEqual(agent.state("active_attempt"),{"synthetic":"first-installation"})

if __name__=="__main__":unittest.main()
