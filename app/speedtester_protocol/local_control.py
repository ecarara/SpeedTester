# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Bounded, authenticated loopback IPC. No credentials cross this interface."""
from collections import OrderedDict
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
import json
import secrets
import threading
import time
import urllib.request
from .crypto import canonical
from .client import ProtocolError, NoRedirect

MAX_MESSAGE = 16384
CONTROL_PORT = 45873


def signature(key, label, payload):
    return hmac.new(key, label.encode() + b"\0" + canonical(payload), hashlib.sha256).hexdigest()


class Authenticator:
    def __init__(self, key, clock=time.time):
        if len(key) != 32:
            raise ValueError("invalid_control_key")
        self.key, self.clock = key, clock
        self.seen = OrderedDict()

    def request(self, operation, arguments=None):
        payload = {"nonce": secrets.token_hex(24), "at": int(self.clock()),
                   "operation": operation, "arguments": arguments or {}}
        return {"payload": payload, "signature": signature(self.key, "request", payload)}

    def authenticate(self, envelope):
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            raise ProtocolError("local_auth_failed")
        payload = envelope["payload"]
        if not isinstance(payload, dict) or set(payload) != {"nonce", "at", "operation", "arguments"}:
            raise ProtocolError("local_auth_failed")
        proof = envelope["signature"]
        if (not isinstance(proof, str) or len(proof) != 64 or not all(char in "0123456789abcdef" for char in proof)
                or not hmac.compare_digest(proof, signature(self.key, "request", payload))):
            raise ProtocolError("local_auth_failed")
        now = self.clock()
        nonce = payload["nonce"]
        if (type(payload["at"]) is not int or abs(now - payload["at"]) > 30
                or not isinstance(nonce, str) or len(nonce) != 48 or nonce in self.seen
                or not isinstance(payload["arguments"], dict)):
            raise ProtocolError("local_auth_failed")
        # Never evict an unexpired nonce: reject bursts instead of enabling replay.
        while self.seen and next(iter(self.seen.values())) < now - 31:
            self.seen.popitem(last=False)
        if len(self.seen) >= 256:
            raise ProtocolError("local_rate_limited")
        self.seen[nonce] = payload["at"]
        return payload

    def response(self, nonce, result):
        payload = {"nonce": nonce, "result": result}
        return {"payload": payload, "signature": signature(self.key, "response", payload)}

    def verify_response(self, nonce, envelope):
        payload = envelope.get("payload") if isinstance(envelope, dict) else None
        proof = envelope.get("signature") if isinstance(envelope, dict) else None
        if (not isinstance(payload, dict) or set(payload) != {"nonce", "result"}
                or payload["nonce"] != nonce or not isinstance(proof, str) or len(proof) != 64
                or not all(char in "0123456789abcdef" for char in proof)
                or not hmac.compare_digest(proof, signature(self.key, "response", payload))):
            raise ProtocolError("local_auth_failed")
        return payload["result"]


class ControlServer(HTTPServer):
    # Serial processing keeps replay checks and configuration changes ordered.
    def __init__(self, key, dispatch, port=CONTROL_PORT):
        self.auth = Authenticator(key)
        self.dispatch = dispatch
        super().__init__(("127.0.0.1", port), ControlHandler)

    def server_bind(self):
        # Loopback IPC does not need reverse DNS; some native environments have
        # a slow/unavailable resolver even though localhost itself is healthy.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address


class ControlHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        # Bound idle connections before reading even the request line/headers.
        self.connection.settimeout(3)

    def log_message(self, *_args):
        # IPC diagnostics must never print request bodies or local credentials.
        return

    def do_POST(self):
        self.connection.settimeout(3)
        length = self.headers.get("Content-Length", "")
        if (self.path != "/control/v1" or self.headers.get("Origin") is not None
                or self.headers.get("Transfer-Encoding") is not None
                or not length.isdecimal() or not 0 < int(length) <= MAX_MESSAGE):
            self.send_error(400)
            return
        try:
            envelope = json.loads(self.rfile.read(int(length)))
            payload = self.server.auth.authenticate(envelope)
        except (ValueError, ProtocolError, TimeoutError):
            self.send_error(403)
            return
        try:
            result = self.server.dispatch(payload["operation"], payload["arguments"])
        except (ProtocolError, ValueError, OSError):
            # Do not reflect server bodies, arbitrary exceptions, paths or keys.
            result = {"ok": False, "code": "local_operation_failed"}
        body = canonical(self.server.auth.response(payload["nonce"], result))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class ControlClient:
    def __init__(self, key, port=CONTROL_PORT, timeout=35):
        self.auth, self.port, self.timeout = Authenticator(key), port, timeout
        # Loopback control must never go through a configured HTTP proxy.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(self, operation, arguments=None):
        request = self.auth.request(operation, arguments)
        body = canonical(request)
        if len(body) > MAX_MESSAGE:
            raise ValueError("local_request_too_large")
        message = urllib.request.Request(f"http://127.0.0.1:{self.port}/control/v1", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with self.opener.open(message, timeout=self.timeout) as response:
            raw = response.read(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE:
                raise ProtocolError("local_response_too_large")
        return self.auth.verify_response(request["payload"]["nonce"], json.loads(raw))


def serve_in_thread(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
