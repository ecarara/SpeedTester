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


def target_identifier(host, port, scope, authentication="none"):
    value = {"runner":"iperf3","host":host,"port":port,"scope":scope}
    if authentication != "none":
        value["authentication"] = authentication
    return "central-" + digest(value)


class TargetRequest(StrictModel):
    request_id: Identifier


class TestTarget(StrictModel):
    protocol_version: Literal['1'] = '1'
    request_id: Identifier
    client_id: Identifier
    runner: Literal['iperf3'] = 'iperf3'
    target_id: str = Field(pattern=r'^central-[0-9a-f]{64}$')
    target_scope: Literal['unconfirmed', 'lan', 'external-controlled']
    authentication: Literal['none', 'rsa-ephemeral-v1'] = 'none'
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
        if self.target_id!=target_identifier(self.host,self.port,self.target_scope,self.authentication):
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
        target_scope=target.target_scope, expires_at=target.expires_at,
        authorize=(lambda grant: obtain_access(client, target, grant)) if target.authentication == "rsa-ephemeral-v1" else None)
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


class TargetAccess(StrictModel):
    request_id: Identifier
    attempt_id: Identifier
    client_id: Identifier
    target_id: str = Field(pattern=r'^central-[0-9a-f]{64}$')
    host: str = Field(min_length=1, max_length=253)
    upload_port: int = Field(ge=1, le=65535)
    download_port: int = Field(ge=1, le=65535)
    username: Identifier
    password: str = Field(min_length=32, max_length=128, repr=False)
    rsa_public_key: str = Field(min_length=200, max_length=4096)
    expires_at: int = Field(ge=0)


def obtain_access(client, target, grant):
    """Obtain per-attempt, one-use endpoints only after the signed start receipt."""
    request_id = str(uuid4())
    body = client.request("POST", "/api/v1/attempts/" + grant.attempt_id + "/target-access", {"request_id": request_id})
    try:
        access = TargetAccess.model_validate(verify(body, client.server_key, "target-access-v1"))
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        key = load_pem_public_key(access.rsa_public_key.encode())
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise ValueError("invalid RSA public key")
        if (access.request_id != request_id or access.client_id != grant.client_id
                or access.attempt_id != grant.attempt_id or access.username != grant.attempt_id
                or access.target_id != grant.target_id or target.target_id != grant.target_id
                or access.host != target.host or access.upload_port == access.download_port
                or not int(time.time()) < access.expires_at <= int(time.time()) + 30):
            raise ValueError("target access binding mismatch")
        return access
    except Exception as exc:
        raise ProtocolError("invalid_target_access") from exc
