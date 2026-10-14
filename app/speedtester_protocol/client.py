# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Real protocol consumer; HTTPS only and receipts bound to exact content."""
import json
import urllib.request
import urllib.error
from .crypto import make_dpop, digest, verify
from .models import Grant, Receipt, Manifest


class ProtocolError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class HTTPS:
    def __init__(self, origin):
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("server must be an HTTPS origin")
        self.origin = origin.rstrip("/")
        self.opener = urllib.request.build_opener(NoRedirect())

    def __call__(self, method, path, headers, payload):
        request = urllib.request.Request(self.origin + path, method=method, headers=headers,
                    data=json.dumps(payload, allow_nan=False).encode() if payload is not None else None)
        try:
            with self.opener.open(request, timeout=10) as response:
                data = response.read(65537)
                if len(data) > 65536:
                    raise ProtocolError("response_too_large")
                return response.status, dict(response.headers), json.loads(data)
        except urllib.error.HTTPError as exc:
            # Error bodies may contain untrusted data; only consume a stable code.
            try:
                body = json.loads(exc.read(4096))
                code = body.get("code", "server_rejected")
            except (ValueError, AttributeError):
                code = "server_rejected"
            return exc.code, dict(exc.headers), {"code": code}


class ServerClient:
    def __init__(self, origin, token, possession_key, server_key, *, transport=None, credentials=None):
        self.transport = transport or HTTPS(origin)
        self.origin, self.token, self.possession_key, self.server_key = origin.rstrip("/"), token, possession_key, server_key
        self.nonce = None
        self.credentials = credentials

    def request(self, method, path, payload=None):
        if self.credentials:
            self.credentials.ensure_current()
            self.token = self.credentials.bundle.access_token
            self.nonce = self.credentials.bundle.nonce
        renewed = False
        for _ in range(3):
            headers = {"Authorization": "DPoP " + self.token, "Content-Type": "application/json"}
            if self.nonce:
                headers["DPoP"] = make_dpop(self.possession_key, method, self.origin + path, self.token, self.nonce)
            status, response_headers, body = self.transport(method, path, headers, payload)
            # Transports normalize case; urllib's HTTPMessage is case-insensitive.
            nonce = next((value for name, value in response_headers.items() if name.lower() == "dpop-nonce"), None)
            if status == 401 and body.get("code") == "use_dpop_nonce" and nonce:
                self.nonce = nonce
                continue
            if status == 401 and body.get("code") == "token_expired" and self.credentials and not renewed:
                self.credentials.ensure_current(force=True)
                self.token, self.nonce = self.credentials.bundle.access_token, self.credentials.bundle.nonce
                renewed = True
                continue
            if status >= 400:
                raise ProtocolError(body.get("code", "server_rejected"))
            if not isinstance(body, dict):
                raise ProtocolError("invalid_response")
            return body
        raise ProtocolError("proof_not_accepted")

    def grant(self, request):
        body = self.request("POST", "/api/v1/measurement-grants", request)
        try:
            grant = Grant.model_validate(verify(body, self.server_key, "grant-v1"))
            if grant.profile_digest != digest(request["profile"]) or grant.runner != request["runner"]:
                raise ValueError("mismatched grant")
            return grant
        except Exception as exc:
            raise ProtocolError("invalid_grant") from exc

    def start(self, grant):
        body = self.request("POST", "/api/v1/attempts/" + grant.attempt_id + "/start")
        return self.receipt(body, "started", grant.attempt_id, digest(grant.model_dump()))

    def receipt(self, body, kind, attempt_id, expected_digest, observation_id=None):
        try:
            receipt = Receipt.model_validate(verify(body, self.server_key, "receipt-v1"))
            if (receipt.kind, receipt.attempt_id, receipt.digest, receipt.observation_id) != (kind, attempt_id, expected_digest, observation_id):
                raise ValueError("mismatched receipt")
            return body
        except Exception as exc:
            raise ProtocolError("invalid_receipt") from exc

    def observation(self, envelope):
        payload = envelope["payload"]
        body = self.request("POST", "/api/v1/metric-observations", envelope)
        return self.receipt(body, "observation", payload["attempt_id"], digest(payload), payload["observation_id"])

    def finalize(self, envelope):
        payload = envelope["payload"]
        body = self.request("POST", "/api/v1/attempts/" + payload["attempt_id"] + "/finalize", envelope)
        return self.receipt(body, "manifest", payload["attempt_id"], digest(payload))
