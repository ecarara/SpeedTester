# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Headless pairing and durable, possession-bound rotating credentials."""
import time
from uuid import uuid4
from .client import HTTPS, ProtocolError, ServerClient
from .crypto import sign, verify, b64, public_bytes, make_dpop, digest
from .models import PairingRequest, Pairing, CredentialBundle


ROTATION_SUFFIX=":rotation"
JSON_CONTENT_TYPE="application/json"


class Credentials:
    def __init__(self, origin, possession_key, server_key, queue, *, transport=None):
        self.origin = HTTPS(origin).origin
        self.possession_key, self.server_key, self.queue = possession_key, server_key, queue
        self.transport = transport or HTTPS(self.origin)
        self.identity = b64(public_bytes(possession_key))
        self.scope = digest({"origin": self.origin, "server": b64(public_bytes(server_key)), "possession": self.identity})
        stored = queue.state(self.scope + ":credentials")
        self.bundle = CredentialBundle.model_validate(stored) if stored else None

    def accept(self, envelope, request_id, client_id=None):
        try:
            bundle = CredentialBundle.model_validate(verify(envelope, self.server_key, "credentials-v1"))
            now = int(time.time())
            if (bundle.request_id != request_id or bundle.possession_key != self.identity or
                (client_id is not None and bundle.client_id != client_id) or
                not now < bundle.expires_at <= now + 900 or
                not bundle.expires_at < bundle.refresh_expires_at <= now + 31 * 86400):
                raise ValueError("credential binding mismatch")
        except Exception as exc:
            raise ProtocolError("invalid_credentials") from exc
        # Replacing the tokens and clearing the pending rotation must be atomic.
        self.queue.put_batch([], self.scope, state_updates={self.scope + ":credentials": bundle.model_dump(), self.scope + ROTATION_SUFFIX: None})
        self.bundle = bundle
        return bundle

    def ensure_current(self, *, force=False):
        if self.bundle is None:
            raise ProtocolError("pairing_required")
        pending = self.queue.state(self.scope + ROTATION_SUFFIX)
        if not pending and not force and self.bundle.expires_at > int(time.time()) + 60:
            return
        if self.bundle.refresh_expires_at <= int(time.time()):
            raise ProtocolError("pairing_required")
        if not pending:
            pending = {"request_id": str(uuid4()), "refresh_token": self.bundle.refresh_token, "nonce": self.bundle.nonce}
            self.queue.state(self.scope + ROTATION_SUFFIX, pending)
        path = "/api/v1/credentials/rotate"
        proof = make_dpop(self.possession_key, "POST", self.origin + path, pending["refresh_token"], pending["nonce"])
        status, _, body = self.transport("POST", path, {"Authorization": "DPoP " + pending["refresh_token"], "DPoP": proof, "Content-Type": JSON_CONTENT_TYPE}, {"request_id": pending["request_id"]})
        if status >= 400:
            raise ProtocolError(body.get("code", "renewal_rejected"))
        self.accept(body, pending["request_id"], self.bundle.client_id)

    def client(self):
        self.ensure_current()
        return ServerClient(self.origin, self.bundle.access_token, self.possession_key, self.server_key, transport=self.transport, credentials=self)


class PairingClient:
    def __init__(self, credentials, measurement_key):
        self.credentials, self.measurement_key = credentials, measurement_key
        self.scope = credentials.scope + ":pairing"

    def begin(self, label="SpeedTester Client", *, reset=False):
        current = None if reset else self.credentials.queue.state(self.scope)
        if current and current.get("pairing") and current["pairing"]["expires_at"] > int(time.time()):
            return Pairing.model_validate(current["pairing"])
        request = current.get("request") if current else None
        if not request or abs(request["issued_at"] - int(time.time())) > 60:
            request = PairingRequest(request_id=str(uuid4()), issued_at=int(time.time()), label=label,
                possession_key=self.credentials.identity, measurement_key=b64(public_bytes(self.measurement_key))).model_dump()
        self.credentials.queue.state(self.scope, {"request": request})
        envelope = sign(request, self.credentials.possession_key, "pairing-request-v1")
        status, _, body = self.credentials.transport("POST", "/api/v1/pairings", {"Content-Type": JSON_CONTENT_TYPE}, envelope)
        if status >= 400:
            raise ProtocolError(body.get("code", "pairing_rejected"))
        try:
            pairing = Pairing.model_validate(verify(body, self.credentials.server_key, "pairing-v1"))
            if (pairing.request_id != request["request_id"] or pairing.possession_key != self.credentials.identity or
                pairing.verification_uri != self.credentials.origin + "/pair" or
                not int(time.time()) < pairing.expires_at <= int(time.time()) + 600):
                raise ValueError("pairing binding mismatch")
        except Exception as exc:
            raise ProtocolError("invalid_pairing") from exc
        self.credentials.queue.state(self.scope, {"request": request, "pairing": pairing.model_dump()})
        return pairing

    def poll(self, pairing):
        path = "/api/v1/pairings/token"
        proof = make_dpop(self.credentials.possession_key, "POST", self.credentials.origin + path, pairing.device_code, pairing.nonce)
        status, _, body = self.credentials.transport("POST", path,
            {"Authorization": "DPoP " + pairing.device_code, "DPoP": proof, "Content-Type": JSON_CONTENT_TYPE}, {})
        if status >= 400:
            raise ProtocolError(body.get("code", "pairing_rejected"))
        return self.credentials.accept(body, pairing.request_id)
