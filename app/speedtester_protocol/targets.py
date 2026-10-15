# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Short-lived, centrally signed destinations; fetching never probes a target."""
import re
import time
from uuid import uuid4
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .client import ProtocolError
from .crypto import digest, verify
from .models import Identifier, StrictModel
from .runner import IperfRunner


def target_identifier(host, port, scope):
    return "central-"+digest({"runner":"iperf3","host":host,"port":port,"scope":scope})


class TargetRequest(StrictModel):
    request_id: Identifier


class TestTarget(StrictModel):
    protocol_version: Literal['1'] = '1'
    request_id: Identifier
    client_id: Identifier
    runner: Literal['iperf3'] = 'iperf3'
    target_id: str = Field(pattern=r'^central-[0-9a-f]{64}$')
    target_scope: Literal['unconfirmed', 'lan', 'external-controlled']
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    issued_at: int = Field(ge=0)
    expires_at: int = Field(ge=0)

    @field_validator('host')
    @classmethod
    def valid_host(cls, value):
        if not re.fullmatch(r'[A-Za-z0-9:.\[\]-]{1,253}', value) or value.startswith('-'):
            raise ValueError('invalid_target_host')
        return value

    @model_validator(mode='after')
    def bounded_lifetime(self):
        if self.target_id!=target_identifier(self.host,self.port,self.target_scope):
            raise ValueError('target_binding_mismatch')
        if not 1 <= self.expires_at-self.issued_at <= 300:
            raise ValueError('invalid_target_lifetime')
        return self


def obtain_target(client, client_id):
    request_id=str(uuid4())
    try:
        body=client.request('POST', '/api/v1/test-target', {'request_id':request_id})
    except ProtocolError as exc:
        if exc.code in {'server_rejected','not_found'}:
            raise ProtocolError('test_target_unavailable') from exc
        raise
    try:
        target=TestTarget.model_validate(verify(body, client.server_key, 'test-target-v1'))
        now=int(time.time())
        if target.request_id!=request_id or target.client_id!=client_id or not target.issued_at-30<=now<target.expires_at:
            raise ValueError('target_context_mismatch')
        return target
    except Exception as exc:
        raise ProtocolError('invalid_test_target') from exc


def automatic_runner(client, client_id, execute=None):
    target=obtain_target(client, client_id)
    bound=IperfRunner(target.host, target.port, target_id=target.target_id,
        target_scope=target.target_scope, expires_at=target.expires_at)
    def validate(grant):
        try:
            bound.check_policy(grant)
        except ValueError as exc:
            raise ProtocolError("test_target_changed") from exc
    if execute is None:
        bound.validate_grant=validate
        return bound
    def checked(grant):
        validate(grant)
        return execute(grant)
    checked.validate_grant=validate
    return checked
