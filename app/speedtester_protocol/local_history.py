# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Read-only bounded local history. No network, token renewal, grant or runner."""

from contextlib import closing
import sqlite3
import time
from typing import Literal
from cryptography.exceptions import InvalidSignature
from nacl.exceptions import CryptoError
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import Field
from .crypto import digest, unb64, verify
from .models import StrictModel, Observation, Manifest, Receipt

PAGE_SIZE = 25
SCAN_LIMIT = 512
MAX_TIMESTAMP = 253402300799
RECORD_ERRORS = (ValueError, KeyError, TypeError, CryptoError, InvalidSignature)
# Bound encrypted input before allocating/decrypting. Neither query mutates SQLite.
ENTRY_FIELDS = "id,CASE WHEN length(ciphertext)<=16384 THEN ciphertext END,status,CASE WHEN length(receipt)<=8192 THEN receipt END"


class HistoryQuery(StrictModel):
    metric: Literal[
        "download",
        "upload",
        "latency",
        "jitter",
        "packet_loss",
        "duration",
        "transfer",
        "tcp_retransmits",
    ] = "download"
    delivery: Literal["all", "pending", "accepted", "quarantined"] = "all"
    days: Literal[0, 1, 7, 30] = 7
    before: int | None = Field(default=None, ge=1, le=2**63 - 1)


def destination_for(installed):
    return digest(
        {
            "origin": installed["origin"],
            "server_key": unb64(installed["server_key"]).hex(),
            "possession_key": Ed25519PrivateKey.from_private_bytes(
                bytes.fromhex(installed["possession_private"])
            )
            .public_key()
            .public_bytes_raw()
            .hex(),
        }
    )


class _HistoryReader:
    def __init__(self, queue, installed, query, result, now):
        self.queue, self.query, self.result = queue, query, result
        self.destination = destination_for(installed)
        self.measurement = Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex(installed["measurement_private"])
        ).public_key()
        self.server = Ed25519PublicKey.from_public_bytes(unb64(installed["server_key"]))
        self.profile_digest = digest(installed["profile"])
        self.cutoff = now - query.days * 86400 if query.days else 0
        self.manifests = {}

    def receipt(self, identifier, sealed, kind, model, payload):
        if sealed is None:
            raise ValueError("missing receipt")
        receipt = Receipt.model_validate(
            verify(
                self.queue.open(sealed, identifier + ":receipt"),
                self.server,
                "receipt-v1",
            )
        )
        if receipt.accepted_at > MAX_TIMESTAMP:
            raise ValueError("unsupported receipt timestamp")
        expected = (
            kind,
            model.attempt_id,
            digest(payload),
            identifier if kind == "observation" else None,
        )
        actual = (
            receipt.kind,
            receipt.attempt_id,
            receipt.digest,
            receipt.observation_id,
        )
        if actual != expected:
            raise ValueError("receipt mismatch")
        return receipt

    def unpack(self, identifier, ciphertext, status, sealed):
        if ciphertext is None:
            raise ValueError("oversized record")
        record = self.queue.open(ciphertext, identifier + ":" + self.destination)
        kind = record["kind"]
        if kind not in {"observation", "manifest"} or record["id"] != identifier:
            raise ValueError("invalid local kind")
        payload = verify(record["envelope"], self.measurement, kind + "-v1")
        model = (
            Observation.model_validate(payload)
            if kind == "observation"
            else Manifest.model_validate(payload)
        )
        if (
            model.observation_id if kind == "observation" else model.attempt_id
        ) != identifier:
            raise ValueError("record id mismatch")
        if kind == "observation" and model.measured_at > MAX_TIMESTAMP:
            raise ValueError("unsupported timestamp")
        if status == "accepted":
            receipt = self.receipt(identifier, sealed, kind, model, payload)
        elif status in {"pending", "quarantined"}:
            receipt = None
        else:
            raise ValueError("invalid delivery state")
        return kind, model, receipt

    def summary(self, conn):
        key = self.destination + ":last_confirmed_at"
        saved = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        if saved:
            try:
                value = self.queue.open(saved[0], key)
                if type(value) is int and 0 <= value <= MAX_TIMESTAMP:
                    self.result["last_confirmed_at"] = value
            except RECORD_ERRORS:
                self.result["unreadable"] += 1
        self.result["confirmation_scope"] = (
            "saved" if self.result["last_confirmed_at"] is not None else "page"
        )
        for status, count in conn.execute(
            "SELECT status,COUNT(*) FROM entries WHERE destination=? GROUP BY status",
            (self.destination,),
        ):
            if status in self.result["counts"]:
                self.result["counts"][status] = count

    def complete(self, conn, model):
        if model.attempt_id in self.manifests:
            return self.manifests[model.attempt_id]
        entry = conn.execute(
            "SELECT " + ENTRY_FIELDS + " FROM entries WHERE id=? AND destination=?",
            (model.attempt_id, self.destination),
        ).fetchone()
        complete = False
        if entry:
            try:
                kind, manifest, receipt = self.unpack(*entry)
                complete = bool(
                    kind == "manifest"
                    and receipt
                    and manifest.observations.get(model.metric)
                    == digest(model.model_dump())
                )
            except RECORD_ERRORS:
                pass
        self.manifests[model.attempt_id] = complete
        return complete

    def matches(self, kind, model, status):
        if kind != "observation":
            return False
        return (
            model.metric == self.query.metric
            and model.measured_at >= self.cutoff
            and self.query.delivery in {"all", status}
        )

    def inspect(self, conn, entry):
        _, identifier, ciphertext, status, sealed = entry
        kind, model, receipt = self.unpack(identifier, ciphertext, status, sealed)
        if receipt:
            self.result["last_confirmed_at"] = max(
                self.result["last_confirmed_at"] or 0, receipt.accepted_at
            )
        if not self.matches(kind, model, status):
            return
        self.result["rows"].append(
            {
                "at": model.measured_at,
                "metric": model.metric,
                "unit": model.unit,
                "value": model.value,
                "quality": model.status,
                "delivery": status,
                "attempt_complete": bool(receipt and self.complete(conn, model)),
                "accepted_at": receipt.accepted_at if receipt else None,
                "current_profile": model.profile_digest == self.profile_digest,
            }
        )

    def read(self, conn):
        self.summary(conn)
        floor = self.query.before or 2**63 - 1
        rows = conn.execute(
            "SELECT rowid,"
            + ENTRY_FIELDS
            + " FROM entries WHERE destination=? AND rowid<? ORDER BY rowid DESC LIMIT ?",
            (self.destination, floor, SCAN_LIMIT),
        ).fetchall()
        for entry in rows:
            self.result["scanned"] += 1
            try:
                self.inspect(conn, entry)
            except RECORD_ERRORS:
                self.result["unreadable"] += 1
            if len(self.result["rows"]) >= PAGE_SIZE:
                break
        # Advance through corrupt/filtered rows too; an empty page may have a cursor.
        if rows and (self.result["scanned"] < len(rows) or len(rows) == SCAN_LIMIT):
            self.result["next_cursor"] = rows[self.result["scanned"] - 1][0]


def read_history(queue, installed, query, *, now=None):
    query = HistoryQuery.model_validate(query)
    result = {
        "rows": [],
        "next_cursor": None,
        "scanned": 0,
        "unreadable": 0,
        "counts": {"accepted": 0, "pending": 0, "quarantined": 0},
        "last_confirmed_at": None,
        "query": query.model_dump(),
    }
    if installed:
        reader = _HistoryReader(
            queue, installed, query, result, int(time.time()) if now is None else now
        )
        with closing(
            sqlite3.connect(queue.path.as_uri() + "?mode=ro", uri=True, timeout=3)
        ) as conn:
            conn.execute("PRAGMA query_only=ON")
            reader.read(conn)
    return result
