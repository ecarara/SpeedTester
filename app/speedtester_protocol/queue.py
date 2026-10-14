# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Encrypted authoritative queue with immutable entries and durable receipts."""
from contextlib import contextmanager
import json
import os
import sqlite3
from pathlib import Path
import secrets
from nacl.bindings import crypto_aead_xchacha20poly1305_ietf_encrypt, crypto_aead_xchacha20poly1305_ietf_decrypt
from .crypto import canonical, digest


class EncryptedQueue:
    def __init__(self, directory, key):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.directory.is_symlink() or len(key) != 32:
            raise ValueError("invalid protected queue")
        os.chmod(self.directory, 0o700)
        self.key = key
        self.path = self.directory / "index.sqlite"
        if self.path.is_symlink():
            raise ValueError("invalid queue index")
        with self.connection() as conn:
            conn.executescript("""CREATE TABLE IF NOT EXISTS entries (
                id TEXT PRIMARY KEY, ciphertext BLOB NOT NULL, destination TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', receipt BLOB);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY,value BLOB NOT NULL);""")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        conn=sqlite3.connect(self.path,timeout=10)
        try:
            with conn:yield conn
        finally:conn.close()

    def seal(self, value, context):
        nonce = secrets.token_bytes(24)
        return nonce + crypto_aead_xchacha20poly1305_ietf_encrypt(canonical(value), context.encode(), nonce, self.key)

    def open(self, value, context):
        return json.loads(crypto_aead_xchacha20poly1305_ietf_decrypt(value[24:], context.encode(), value[:24], self.key))

    def put(self,record,destination):
        return self.put_batch([record],destination)

    def put_batch(self,records,destination,*,state_updates=None):
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for record in records:
                identifier=record["id"]
                context=identifier+":"+destination
                old=conn.execute("SELECT ciphertext,destination FROM entries WHERE id=?",(identifier,)).fetchone()
                if old:
                    if old[1]!=destination or self.open(old[0],context)!=record:
                        raise ValueError("queue identifier conflict")
                    continue
                conn.execute("INSERT INTO entries(id,ciphertext,destination) VALUES(?,?,?)",(identifier,self.seal(record,context),destination))

            for key,value in (state_updates or {}).items():
                conn.execute("INSERT OR REPLACE INTO state VALUES(?,?)",(key,self.seal(value,key)))

    def pending(self, destination):
        return self.records(destination, "pending")

    def quarantined(self, destination):
        return self.records(destination, "quarantined")

    def records(self, destination, status):
        with self.connection() as conn:
            rows = conn.execute("SELECT id,ciphertext FROM entries WHERE status=? AND destination=? ORDER BY rowid", (status,destination)).fetchall()
        return [self.open(row[1], row[0]+":"+destination) for row in rows]

    def quarantine_attempt(self,destination,attempt_id,code,*,grant=None,request_id=None):
        """Preserve terminal evidence; never manufacture an acceptance receipt."""
        active_key=destination+":active_attempt"
        request_key=destination+":grant_request"
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if attempt_id is not None:
                rows=conn.execute("SELECT id,ciphertext FROM entries WHERE destination=? AND status='pending'",(destination,)).fetchall()
                for identifier,ciphertext in rows:
                    record=self.open(ciphertext,identifier+":"+destination)
                    if record["envelope"]["payload"]["attempt_id"]==attempt_id:
                        conn.execute("UPDATE entries SET status='quarantined' WHERE id=? AND status='pending'",(identifier,))
            evidence_key=destination+":quarantine:"+(attempt_id or request_id)
            evidence={"attempt_id":attempt_id,"request_id":request_id,"code":code,"grant":grant}
            conn.execute("INSERT OR REPLACE INTO state VALUES(?,?)",(evidence_key,self.seal(evidence,evidence_key)))
            row=conn.execute("SELECT value FROM state WHERE key=?",(active_key,)).fetchone()
            active=self.open(row[0],active_key) if row else None
            request_row=conn.execute("SELECT value FROM state WHERE key=?",(request_key,)).fetchone()
            current_request=self.open(request_row[0],request_key) if request_row else None
            # A terminal older attempt cannot clear a different live attempt.
            if (active and active["attempt_id"]==attempt_id) or (not active and (request_id is None or request_id==current_request)):
                from uuid import uuid4
                for key,value in ((active_key,None),(request_key,str(uuid4()))):
                    conn.execute("INSERT OR REPLACE INTO state VALUES(?,?)",(key,self.seal(value,key)))

    def acknowledge(self, identifier, receipt,*,previous_receipt_key="previous_receipt"):
        # Caller must verify the server signature AND record binding first.
        with self.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE entries SET status='accepted',receipt=? WHERE id=?",(self.seal(receipt,identifier+":receipt"),identifier))
            if receipt["payload"]["kind"]=="manifest":
                conn.execute("INSERT OR REPLACE INTO state VALUES(?,?)",(previous_receipt_key,self.seal(digest(receipt),previous_receipt_key)))

    def state(self, key, value=None):
        with self.connection() as conn:
            if value is not None:
                conn.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, self.seal(value, key)))
            row = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return self.open(row[0], key) if row else None
