# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Capture runner output only after central authorization; no manual metrics API."""
import math
import time
from uuid import uuid4
from .crypto import digest,sign
from .models import Observation,Manifest,METRICS
from .client import ProtocolError


TERMINAL_ATTEMPT_CODES=frozenset({"start_expired","grant_expired","attempt_expired","legal_context_changed","test_target_changed","machine_identity_required","schedule_update_required"})


class CommunityAgent:
    def __init__(self,client,queue,measurement_key,profile,runner,*,schedule_slot=None):
        self.client,self.queue,self.key,self.profile,self.runner=client,queue,measurement_key,profile,runner
        self.schedule_slot=schedule_slot
        self.destination=digest({"origin":client.origin,"server_key":client.server_key.public_bytes_raw().hex(),"possession_key":client.possession_key.public_key().public_bytes_raw().hex()})

    def state(self,key,value=None):
        return self.queue.state(self.destination+":"+key,value)

    def sync(self):
        completed=0;quarantined=set()
        for record in self.queue.pending(self.destination):
            attempt_id=record["envelope"]["payload"]["attempt_id"]
            if attempt_id in quarantined:continue
            try:
                if record["kind"]=="observation":receipt=self.client.observation(record["envelope"])
                else:receipt=self.client.finalize(record["envelope"])
            except ProtocolError as exc:
                if exc.code not in TERMINAL_ATTEMPT_CODES:raise
                self.queue.quarantine_attempt(self.destination,attempt_id,exc.code)
                quarantined.add(attempt_id)
                continue
            self.queue.acknowledge(record["id"],receipt,previous_receipt_key=self.destination+":previous_receipt")
            confirmed_at = receipt["payload"].get("accepted_at")
            if type(confirmed_at) is int:
                self.state("last_confirmed_at", max(self.state("last_confirmed_at") or 0, confirmed_at))
            completed+=1
        return completed

    def _quarantine(self,code,grant=None,request_id=None):
        self.queue.quarantine_attempt(self.destination,grant.attempt_id if grant else None,code,
            grant=grant.model_dump() if grant else None,request_id=request_id)

    @staticmethod
    def value(result,attribute,multiplier):
        value=getattr(result,attribute,None)
        if value is None:return None
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError("invalid runner metric")
        return round(value*multiplier)

    def _authorize(self,validate=None):
        request_id=self.state("grant_request")
        if request_id is None:
            request_id=str(uuid4());self.state("grant_request",request_id)
        request={"request_id":request_id,"profile":self.profile.model_dump(),"runner":self.runner}
        if self.schedule_slot is not None:
            request["schedule_slot"]=self.schedule_slot
        grant=self.client.grant(request)
        # Persist verified evidence before checking the start window.
        self.state("active_attempt",grant.model_dump())
        if grant.start_before<int(time.time()):raise ProtocolError("grant_expired")
        if validate:
            validate(grant)
        self.client.start(grant)
        return grant

    def run_once(self,execute,*,allow_new=True):
        from .models import Grant
        self.sync()
        # At most one fresh retry after terminal recovery, never an unbounded loop.
        for _ in range(2):
            try:
                active=self.state("active_attempt")
                if active:
                    grant=Grant.model_validate(active)
                    # A restarted process never executes a previously active grant.
                    self.client.start(grant)
                    return self._complete(grant,dict.fromkeys(METRICS),True,grant.issued_at)
                if not allow_new:
                    return None
                return self._measure(self._authorize(getattr(execute,"__dict__",{}).get("validate_grant")),execute)
            except ProtocolError as exc:
                if exc.code not in TERMINAL_ATTEMPT_CODES:raise
                active=self.state("active_attempt")
                grant=Grant.model_validate(active) if active else None
                self._quarantine(exc.code,grant,self.state("grant_request"))
        raise ProtocolError("terminal_attempt_recovery_pending")

    def _measure(self,grant,execute):
        measured_at=int(time.time())
        failure=False
        try:
            result=execute(grant)
            values={
                "download":self.value(result,"download_mbps",1_000_000),
                "upload":self.value(result,"upload_mbps",1_000_000),
                "latency":self.value(result,"ping_ms",1000),
                "jitter":self.value(result,"jitter_ms",1000),
                "packet_loss":self.value(result,"packet_loss_pct",10000),
                "duration":self.value(result,"duration_sec",1000),
                "transfer":self.value(result,"transfer_bytes",1),
                "tcp_retransmits":self.value(result,"tcp_retransmits",1),
            }
        except Exception:
            failure=True;values=dict.fromkeys(METRICS)
        return self._complete(grant,values,failure,measured_at)

    @staticmethod
    def _value_status(value):
        return "valid" if value is not None else "not-supported"

    def _complete(self,grant,values,failure,measured_at):
        records=[];checksums={}
        for metric,(unit,_,_) in METRICS.items():
            value=values[metric]
            method=self.runner+":throughput" if metric in {"download","upload","duration","transfer","tcp_retransmits"} else self.runner+":reported-"+metric
            status="error" if failure else self._value_status(value)
            observation=Observation(observation_id=str(uuid4()),attempt_id=grant.attempt_id,metric=metric,unit=unit,value=value,
                status=status,method=method,
                measured_at=measured_at,nonce=grant.nonce,profile_digest=grant.profile_digest,legal_digest=grant.legal_digest)
            payload=observation.model_dump();checksums[metric]=digest(payload)
            records.append({"id":observation.observation_id,"kind":"observation","envelope":sign(payload,self.key,"observation-v1")})
        # The signed grant carries the Server chain head, including lost receipts.
        previous=grant.previous_receipt
        manifest=Manifest(attempt_id=grant.attempt_id,nonce=grant.nonce,profile_digest=grant.profile_digest,
                          legal_digest=grant.legal_digest,previous_receipt=previous,observations=checksums)
        records.append({"id":grant.attempt_id,"kind":"manifest","envelope":sign(manifest.model_dump(),self.key,"manifest-v1")})
        # All captured metrics and their manifest enter the encrypted queue atomically.
        self.queue.put_batch(records,self.destination,state_updates={self.destination+":grant_request":str(uuid4()),self.destination+":active_attempt":None})
        self.sync()
        return grant.attempt_id
