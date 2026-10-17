# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Synthetic signed records only. No runner, measurements or server connection."""

import copy
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from speedtester_protocol.crypto import sign, digest, b64, canonical
from speedtester_protocol.models import METRICS, Observation, Manifest, Receipt
from speedtester_protocol.queue import EncryptedQueue
from speedtester_protocol.local_history import (
    read_history,
    destination_for,
    HistoryQuery,
)


def history_fixture(queue):
    server, possession, measurement = (Ed25519PrivateKey.generate() for _ in range(3))
    profile = {
        "version": 1,
        "operator": "SYNTHETIC",
        "country_code": "ZZ",
        "region": "TEST",
        "city": "TEST",
        "access_type": "fiber",
        "link_type": "ethernet",
    }
    installed = {
        "origin": "https://server.example",
        "server_key": b64(server.public_key().public_bytes_raw()),
        "possession_private": possession.private_bytes_raw().hex(),
        "measurement_private": measurement.private_bytes_raw().hex(),
        "profile": profile,
    }
    return installed, server, measurement


def add_attempt(
    queue,
    installed,
    server,
    measurement,
    *,
    at=None,
    delivery="pending",
    closed=True,
    profile=None,
):
    attempt = str(uuid4())
    destination = destination_for(installed)
    records = []
    checksums = {}
    values = {
        "download": 120_000_000,
        "upload": 60_000_000,
        "latency": None,
        "jitter": None,
        "packet_loss": None,
        "duration": 20_000,
        "transfer": 1000,
        "tcp_retransmits": 0,
    }
    for metric, (unit, _, _) in METRICS.items():
        payload = Observation(
            observation_id=str(uuid4()),
            attempt_id=attempt,
            metric=metric,
            unit=unit,
            value=values[metric],
            status="valid" if values[metric] is not None else "not-supported",
            method="iperf3:throughput",
            measured_at=int(time.time()) if at is None else at,
            nonce="a" * 32,
            profile_digest=digest(profile or installed["profile"]),
            legal_digest="b" * 64,
        ).model_dump()
        checksums[metric] = digest(payload)
        records.append(
            {
                "id": payload["observation_id"],
                "kind": "observation",
                "envelope": sign(payload, measurement, "observation-v1"),
            }
        )
    manifest = Manifest(
        attempt_id=attempt,
        nonce="a" * 32,
        profile_digest=digest(profile or installed["profile"]),
        legal_digest="b" * 64,
        observations=checksums,
    ).model_dump()
    records.append(
        {
            "id": attempt,
            "kind": "manifest",
            "envelope": sign(manifest, measurement, "manifest-v1"),
        }
    )
    queue.put_batch(records, destination)
    if delivery == "accepted":
        for record in records:
            if record["kind"] == "manifest" and not closed:
                continue
            receipt = Receipt(
                attempt_id=attempt,
                observation_id=record["id"]
                if record["kind"] == "observation"
                else None,
                kind=record["kind"],
                digest=digest(record["envelope"]["payload"]),
                accepted_at=int(time.time()),
            ).model_dump()
            queue.acknowledge(record["id"], sign(receipt, server, "receipt-v1"))
    if delivery == "quarantined":
        queue.quarantine_attempt(destination, attempt, "legal_context_changed")
    return records


class LocalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.queue = EncryptedQueue(Path(self.temp.name), b"k" * 32)
        self.installed, self.server, self.measurement = history_fixture(self.queue)

    def add(self, **kwargs):
        return add_attempt(
            self.queue, self.installed, self.server, self.measurement, **kwargs
        )

    def read(self, **query):
        return read_history(self.queue, self.installed, query)

    def test_receipts_distinguish_metric_received_from_complete_test_and_keep_states(
        self,
    ):
        self.add(delivery="accepted")
        self.add(delivery="accepted", closed=False)
        self.add()
        self.add(delivery="quarantined")
        result = self.read()
        self.assertEqual(len(result["rows"]), 4)
        states = {(row["delivery"], row["attempt_complete"]) for row in result["rows"]}
        self.assertEqual(
            states,
            {
                ("accepted", True),
                ("accepted", False),
                ("pending", False),
                ("quarantined", False),
            },
        )
        self.assertEqual(
            result["counts"], {"accepted": 17, "pending": 10, "quarantined": 9}
        )
        self.assertEqual(self.read(metric="latency")["rows"][0]["value"], None)
        self.assertEqual(self.read(metric="tcp_retransmits")["rows"][0]["value"], 0)

    def test_query_is_read_only_scoped_and_does_not_return_secrets_or_raw_envelopes(
        self,
    ):
        self.add(delivery="accepted")
        other = copy.deepcopy(self.installed)
        other["origin"] = "https://another.example"
        add_attempt(self.queue, other, self.server, self.measurement)
        before = hashlib.sha256(self.queue.path.read_bytes()).digest()
        result = self.read()
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(hashlib.sha256(self.queue.path.read_bytes()).digest(), before)
        encoded = canonical(result).decode()
        for value in (
            self.installed["possession_private"],
            self.installed["measurement_private"],
            "signature",
            "nonce",
            "legal_digest",
            "profile_digest",
            "access_token",
            "refresh_token",
        ):
            self.assertNotIn(value, encoded)
        self.assertLess(len(canonical(result)), 12000)

    def test_corrupted_ciphertext_and_receipt_cannot_be_shown_as_verified_or_zero(self):
        records = self.add(delivery="accepted")
        download = records[0]["id"]
        with self.queue.connection() as conn:
            conn.execute(
                "UPDATE entries SET receipt=? WHERE id=?", (b"bad receipt", download)
            )
        result = self.read()
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["unreadable"], 1)
        with self.queue.connection() as conn:
            conn.execute(
                "UPDATE entries SET ciphertext=? WHERE id=?",
                (b"bad ciphertext", download),
            )
        self.assertEqual(self.read()["rows"], [])

    def test_bounded_paging_filters_and_prior_profile_without_rewriting_originals(self):
        now = int(time.time())
        for index in range(60):
            self.add(at=now - index * 60)
        cursors = []
        rows = []
        cursor = None
        for _ in range(6):
            page = self.read(before=cursor)
            self.assertLessEqual(page["scanned"], 512)
            rows += page["rows"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
            self.assertNotIn(cursor, cursors)
            cursors.append(cursor)
        self.assertEqual(len(rows), 60)
        self.assertEqual(self.read(delivery="accepted")["rows"], [])
        self.assertEqual(self.read(days=0)["counts"]["pending"], 540)
        old = copy.deepcopy(self.installed["profile"])
        old["version"] = 2
        self.add(at=now - 40 * 86400, profile=old)
        self.assertEqual(len(self.read(days=0)["rows"]), 25)
        self.assertFalse(self.read(days=0)["rows"][0]["current_profile"])
        self.assertTrue(
            all(row["at"] >= now - 86400 for row in self.read(days=1)["rows"])
        )

    def test_invalid_query_and_oversized_data_are_rejected_or_bounded(self):
        for query in (
            {"before": 0},
            {"before": True},
            {"before": 2**70},
            {"metric": "secret"},
            {"days": 999},
            {"limit": 1000000},
            {"delivery": "unknown"},
        ):
            with self.subTest(query=query), self.assertRaises(ValueError):
                HistoryQuery.model_validate(query)
        self.add()
        with self.queue.connection() as conn:
            conn.execute(
                "UPDATE entries SET ciphertext=? WHERE rowid=1", (b"x" * 20000,)
            )
        self.assertEqual(self.read()["unreadable"], 1)
        self.assertEqual(read_history(self.queue, None, {})["rows"], [])

    def test_forged_observation_and_wrong_record_receipt_are_never_accepted(self):
        records = self.add(delivery="accepted")
        record = records[0]
        identifier = record["id"]
        other = Ed25519PrivateKey.generate()
        record["envelope"] = sign(
            record["envelope"]["payload"], other, "observation-v1"
        )
        context = identifier + ":" + destination_for(self.installed)
        with self.queue.connection() as conn:
            conn.execute(
                "UPDATE entries SET ciphertext=? WHERE id=?",
                (self.queue.seal(record, context), identifier),
            )
        self.assertEqual(self.read()["rows"], [])
        self.assertEqual(self.read()["unreadable"], 1)
        records = self.add(delivery="accepted")
        identifier = records[0]["id"]
        with self.queue.connection() as conn:
            other_receipt = conn.execute(
                "SELECT receipt FROM entries WHERE id=?", (records[1]["id"],)
            ).fetchone()[0]
            envelope = self.queue.open(other_receipt, records[1]["id"] + ":receipt")
            conn.execute(
                "UPDATE entries SET receipt=? WHERE id=?",
                (self.queue.seal(envelope, identifier + ":receipt"), identifier),
            )
        self.assertEqual(self.read()["rows"], [])

    def test_corrupt_manifest_leaves_metric_received_without_claiming_complete_integration(
        self,
    ):
        records = self.add(delivery="accepted")
        with self.queue.connection() as conn:
            conn.execute(
                "UPDATE entries SET receipt=? WHERE id=?", (b"bad", records[-1]["id"])
            )
        result = self.read()
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["delivery"], "accepted")
        self.assertFalse(result["rows"][0]["attempt_complete"])
        self.assertEqual(result["unreadable"], 1)

    def test_local_receipt_timestamp_marker_is_encrypted_and_corruption_preserves_fallback(
        self,
    ):
        self.add(delivery="accepted")
        key = destination_for(self.installed) + ":last_confirmed_at"
        self.queue.state(key, 1234567890)
        result = self.read()
        self.assertEqual(result["confirmation_scope"], "saved")
        self.assertGreater(result["last_confirmed_at"], 1234567890)
        with self.queue.connection() as conn:
            conn.execute("UPDATE state SET value=? WHERE key=?", (b"corrupt", key))
        result = self.read()
        self.assertEqual(result["confirmation_scope"], "page")
        self.assertIsNotNone(result["last_confirmed_at"])
        self.assertEqual(result["unreadable"], 1)

    def test_authenticated_local_ipc_is_read_only_bounded_without_network_or_scheduler_wakeup(
        self,
    ):
        from unittest.mock import Mock
        from speedtester_protocol.desktop_service import DesktopEngine
        from speedtester_protocol.local_control import (
            ControlServer,
            ControlClient,
            serve_in_thread,
            MAX_MESSAGE,
        )
        import secrets

        self.installed["schedule"] = {"timezone": "UTC", "tests_per_period": 2}
        self.queue.state("installation", self.installed)
        # Construct before storing synthetic installation: no startup migration needed.
        self.queue.state("desktop:measurements_enabled", True)
        engine = object.__new__(DesktopEngine)
        import threading

        engine.queue = self.queue
        engine.lock = threading.RLock()
        engine.wake = threading.Event()
        engine.clock = time.time
        engine.maintenance = False
        engine.transport = Mock(side_effect=AssertionError("No network"))
        engine.runner = Mock(side_effect=AssertionError("No measurements"))
        # Credential context is loaded locally; no saved token is needed to consult.
        for _ in range(30):
            self.add(delivery="accepted")
        snapshot = hashlib.sha256(self.queue.path.read_bytes()).digest()
        key = secrets.token_bytes(32)
        server = ControlServer(key, engine.dispatch, port=0)
        thread = serve_in_thread(server)
        self.addCleanup(
            lambda: (server.shutdown(), server.server_close(), thread.join(3))
        )
        client = ControlClient(key, port=server.server_port)
        result = client.call("history", {"days": 0})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["rows"]), 25)
        self.assertLess(
            len(canonical(server.auth.response("a" * 48, result))), MAX_MESSAGE
        )
        self.assertTrue(result["integration"]["enabled"])
        self.assertFalse(result["integration"]["paired"])
        self.assertFalse(engine.wake.is_set())
        engine.transport.assert_not_called()
        engine.runner.assert_not_called()
        self.assertEqual(
            hashlib.sha256(self.queue.path.read_bytes()).digest(), snapshot
        )
        self.assertFalse(client.call("history", {"before": True})["ok"])
        with self.assertRaises(Exception):
            ControlClient(secrets.token_bytes(32), port=server.server_port).call(
                "history"
            )
        self.assertFalse(engine.wake.is_set())
