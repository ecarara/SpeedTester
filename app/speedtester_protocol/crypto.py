# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Canonical JSON, domain-separated Ed25519 and standards-based DPoP."""
import base64
import hashlib
import json
import secrets
import time
from uuid import uuid4
import jwt
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from .models import Envelope


def b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def unb64(value):
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def canonical(payload):
    return rfc8785.dumps(payload)


def digest(payload):
    return hashlib.sha256(canonical(payload)).hexdigest()


def public_bytes(key):
    public = key.public_key() if isinstance(key, Ed25519PrivateKey) else key
    return public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def key_id(key):
    return hashlib.sha256(public_bytes(key)).hexdigest()


def sign(payload, key, domain):
    message = domain.encode("ascii") + b"\0" + canonical(payload)
    return {"payload": payload, "key_id": key_id(key), "signature": b64(key.sign(message))}


def verify(envelope, key, domain):
    envelope = Envelope.model_validate(envelope)
    if envelope.key_id != key_id(key):
        raise ValueError("untrusted signing key")
    key.verify(unb64(envelope.signature), domain.encode("ascii") + b"\0" + canonical(envelope.payload))
    return envelope.payload


def make_dpop(key, method, uri, token, nonce, *, now=None):
    claims = {"jti": str(uuid4()), "iat": int(time.time() if now is None else now),
              "htm": method.upper(), "htu": uri,
              "ath": b64(hashlib.sha256(token.encode("ascii")).digest()), "nonce": nonce}
    return jwt.encode(claims, key, algorithm="EdDSA", headers={"typ": "dpop+jwt",
                      "jwk": {"kty": "OKP", "crv": "Ed25519", "x": b64(public_bytes(key))}})


def proof_header(proof):
    """Parse only the untrusted header; authentication remains in jwt.decode."""
    parts=proof.split(".")
    if len(parts)!=3 or not all(parts):raise ValueError("invalid proof encoding")
    def unique_object(pairs):
        result={}
        for name,value in pairs:
            if name in result:raise ValueError("duplicate proof header member")
            result[name]=value
        return result
    header=json.loads(unb64(parts[0]).decode("utf-8"),object_pairs_hook=unique_object)
    if not isinstance(header,dict):raise ValueError("invalid proof header")
    return header


def check_dpop(proof, public_key, method, uri, token, nonce, *, now=None):
    if not isinstance(proof, str) or len(proof) > 2048:
        raise ValueError("invalid proof")
    header = proof_header(proof)
    expected = {"kty": "OKP", "crv": "Ed25519", "x": b64(public_bytes(public_key))}
    if set(header) != {"alg", "typ", "jwk"} or header["alg"] != "EdDSA" or header["typ"] != "dpop+jwt" or header["jwk"] != expected:
        raise ValueError("invalid proof header")
    claims = jwt.decode(proof, public_key, algorithms=["EdDSA"], options={"verify_iat": False,
                       "require": ["jti", "iat", "htm", "htu", "ath", "nonce"]})
    now = int(time.time() if now is None else now)
    if (type(claims["iat"]) is not int or abs(now - claims["iat"]) > 30 or
            claims["htm"] != method.upper() or claims["htu"] != uri or
            claims["nonce"] != nonce or claims["ath"] != b64(hashlib.sha256(token.encode("ascii")).digest())):
        raise ValueError("invalid proof binding")
    from uuid import UUID
    if str(UUID(claims["jti"])) != claims["jti"]:
        raise ValueError("invalid proof identifier")
    return claims["jti"]
