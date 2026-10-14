# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Capture runner output only after central authorization; no manual metrics API."""
import math
import time
from uuid import uuid4
from .crypto import digest,sign
from .models import Observation,Manifest,METRICS
from .client import ProtocolError


class CommunityAgent:
    def __init__(self,client,queue,measurement_key,profile,runner):
        self.client,self.queue,self.key,self.profile,self.runner=client,queue,measurement_key,profile,runner
        self.destination=digest({"origin":client.origin,"server_key":client.server_key.public_bytes_raw().hex(),"possession_key":client.possession_key.public_key().public_bytes_raw().hex()})

    def state(self,key,value=None):
        return self.queue.state(self.destination+":"+key,value)

    def sync(self):
        completed=0
        for record in self.queue.pending(self.destination):
            if record["kind"]=="observation":receipt=self.client.observation(record["envelope"])
            else:receipt=self.client.finalize(record["envelope"])
            self.queue.acknowledge(record["id"],receipt,previous_receipt_key=self.destination+":previous_receipt")
            completed+=1
        return completed

    @staticmethod
    def value(result,attribute,multiplier):
        value=getattr(result,attribute,None)
        if value is None:return None
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError("invalid runner metric")
        return round(value*multiplier)

    def run_once(self,execute):
        self.sync()
        active=self.state("active_attempt")
        if active:
            from .models import Grant
            grant=Grant.model_validate(active)
            # Start is idempotent. A restarted process never runs the same grant again.
            self.client.start(grant)
            return self._complete(grant,{metric:None for metric in METRICS},True,int(time.time()))
        request_id=self.state("grant_request")
        if request_id is None:
            request_id=str(uuid4());self.state("grant_request",request_id)
        request={"request_id":request_id,"profile":self.profile.model_dump(),"runner":self.runner}
        grant=self.client.grant(request)
        if grant.start_before<int(time.time()):raise ProtocolError("grant_expired")
        self.state("active_attempt",grant.model_dump())
        self.client.start(grant)
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
            failure=True;values={metric:None for metric in METRICS}
        return self._complete(grant,values,failure,measured_at)

    def _complete(self,grant,values,failure,measured_at):
        records=[];checksums={}
        for metric,(unit,_,_) in METRICS.items():
            value=values[metric]
            method=self.runner+":throughput" if metric in {"download","upload","duration","transfer","tcp_retransmits"} else self.runner+":reported-"+metric
            observation=Observation(observation_id=str(uuid4()),attempt_id=grant.attempt_id,metric=metric,unit=unit,value=value,
                status="error" if failure else "valid" if value is not None else "not-supported",method=method,
                measured_at=measured_at,nonce=grant.nonce,profile_digest=grant.profile_digest,legal_digest=grant.legal_digest)
            payload=observation.model_dump();checksums[metric]=digest(payload)
            records.append({"id":observation.observation_id,"kind":"observation","envelope":sign(payload,self.key,"observation-v1")})
        previous=self.state("previous_receipt")
        manifest=Manifest(attempt_id=grant.attempt_id,nonce=grant.nonce,profile_digest=grant.profile_digest,
                          legal_digest=grant.legal_digest,previous_receipt=previous,observations=checksums)
        records.append({"id":grant.attempt_id,"kind":"manifest","envelope":sign(manifest.model_dump(),self.key,"manifest-v1")})
        # All captured metrics and their manifest enter the encrypted queue atomically.
        self.queue.put_batch(records,self.destination,state_updates={self.destination+":grant_request":str(uuid4()),self.destination+":active_attempt":None})
        self.sync()
        return grant.attempt_id
