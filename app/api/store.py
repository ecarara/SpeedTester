# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""SQLite storage layer for speed-test samples.

The database lives at ``settings.db_path`` and holds a single table,
``samples``:

    id            INTEGER PRIMARY KEY AUTOINCREMENT
    started_at    TEXT  (UTC ISO-8601, e.g. 2024-05-01T13:00:00Z)
    is_failure    INTEGER (0 = ok, 1 = failed measurement)
    failure_cause TEXT  (e.g. "network", "power", "server", "timeout", NULL)
    failure_note  TEXT  (free-form justification, NULL)
    download_mbps REAL
    upload_mbps REAL
    ping_ms       REAL
    jitter_ms     REAL
    latency_min_ms REAL
    latency_max_ms REAL
    packet_loss_pct REAL
    tcp_retransmits INTEGER
    server_id     INTEGER
    server_name   TEXT
    server_location TEXT
    country       TEXT
    interface     TEXT      (e.g. "eth0" or "docker0")
    isp           TEXT      (e.g. "Vivo", "Claro", "TIM")
    bandwidth_contracted_mbps REAL  (operator-configured, may be NULL)
    test_duration_sec REAL
    runner TEXT  (fast, ookla, iperf3, or NULL for legacy rows)

All timestamps are stored and returned in UTC (``Z``).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Iterable, List, Optional

SCHEMA_VERSION = 8

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    is_failure INTEGER NOT NULL DEFAULT 0,
    failure_cause TEXT,
    failure_note TEXT,
    download_mbps REAL,
    upload_mbps REAL,
    ping_ms REAL,
    jitter_ms REAL,
    latency_min_ms REAL,
    latency_max_ms REAL,
    packet_loss_pct REAL,
    tcp_retransmits INTEGER,
    server_id INTEGER,
    server_name TEXT,
    server_location TEXT,
    country TEXT,
    interface TEXT,
    isp TEXT,
    bandwidth_contracted_mbps REAL,
    test_duration_sec REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_started_at ON samples(started_at);
CREATE INDEX IF NOT EXISTS idx_samples_failure ON samples(is_failure);
CREATE TABLE IF NOT EXISTS measurement_slots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_date TEXT NOT NULL,
    quadrant TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    scheduled_for TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    schedule_seed TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    classification_note TEXT,
    classification_source TEXT,
    classification_updated_at TEXT,
    UNIQUE(local_date, quadrant, slot_index)
);
CREATE INDEX IF NOT EXISTS idx_slots_scheduled ON measurement_slots(status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_slots_date ON measurement_slots(local_date, quadrant);
CREATE TABLE IF NOT EXISTS availability_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'medium',
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_period ON availability_events(started_at, ended_at);
CREATE TABLE IF NOT EXISTS service_heartbeats (
    service TEXT PRIMARY KEY,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    message TEXT NOT NULL,
    sample_id INTEGER,
    delivered INTEGER NOT NULL DEFAULT 0,
    delivery_error TEXT,
    payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_kind ON alerts(kind, created_at);
CREATE TABLE IF NOT EXISTS measurement_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT,
    metrics_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_slot ON measurement_attempts(slot_id, id);
"""


@dataclass
class Sample:
    """Persisted representative measurement or classified failure.

    ``started_at`` is always UTC. A failure uses the same record shape as a
    successful measurement but leaves speed fields null and records its cause,
    origin and evidence separately.
    """

    started_at: str  # UTC ISO-8601 with trailing Z
    is_failure: bool = False
    failure_cause: Optional[str] = None
    failure_note: Optional[str] = None
    download_mbps: Optional[float] = None
    upload_mbps: Optional[float] = None
    ping_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    latency_min_ms: Optional[float] = None
    latency_max_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None
    tcp_retransmits: Optional[int] = None
    server_id: Optional[int] = None
    server_name: Optional[str] = None
    server_location: Optional[str] = None
    country: Optional[str] = None
    interface: Optional[str] = None
    isp: Optional[str] = None
    bandwidth_contracted_mbps: Optional[float] = None
    test_duration_sec: Optional[float] = None
    slot_id: Optional[int] = None
    local_date: Optional[str] = None
    quadrant: Optional[str] = None
    failure_origin: Optional[str] = None
    power_state: Optional[str] = None
    gateway_reachable: Optional[bool] = None
    external_reachable: Optional[bool] = None
    classification_confidence: Optional[str] = None
    evidence_json: Optional[str] = None
    runner: Optional[str] = None

    def to_row(self) -> tuple:
        """Return values in the exact order used by the INSERT statement."""
        return (
            self.started_at,
            1 if self.is_failure else 0,
            self.failure_cause,
            self.failure_note,
            self.download_mbps,
            self.upload_mbps,
            self.ping_ms,
            self.jitter_ms,
            self.latency_min_ms,
            self.latency_max_ms,
            self.packet_loss_pct,
            self.tcp_retransmits,
            self.server_id,
            self.server_name,
            self.server_location,
            self.country,
            self.interface,
            self.isp,
            self.bandwidth_contracted_mbps,
            self.test_duration_sec,
            self.slot_id,
            self.local_date,
            self.quadrant,
            self.failure_origin,
            self.power_state,
            self.gateway_reachable,
            self.external_reachable,
            self.classification_confidence,
            self.evidence_json,
            self.runner,
        )

    def to_dict(self) -> dict:
        """Return the public JSON-shaped representation of this sample."""
        return {
            "started_at": self.started_at,
            "is_failure": self.is_failure,
            "failure_cause": self.failure_cause,
            "failure_note": self.failure_note,
            "download_mbps": self.download_mbps,
            "upload_mbps": self.upload_mbps,
            "ping_ms": self.ping_ms,
            "jitter_ms": self.jitter_ms,
            "latency_min_ms": self.latency_min_ms,
            "latency_max_ms": self.latency_max_ms,
            "packet_loss_pct": self.packet_loss_pct,
            "tcp_retransmits": self.tcp_retransmits,
            "server_id": self.server_id,
            "server_name": self.server_name,
            "server_location": self.server_location,
            "country": self.country,
            "interface": self.interface,
            "isp": self.isp,
            "bandwidth_contracted_mbps": self.bandwidth_contracted_mbps,
            "test_duration_sec": self.test_duration_sec,
            "slot_id": self.slot_id,
            "local_date": self.local_date,
            "quadrant": self.quadrant,
            "failure_origin": self.failure_origin,
            "power_state": self.power_state,
            "gateway_reachable": self.gateway_reachable,
            "external_reachable": self.external_reachable,
            "classification_confidence": self.classification_confidence,
            "evidence_json": self.evidence_json,
            "runner": self.runner,
        }


@dataclass(frozen=True)
class MeasurementSlot:
    """Expected measurement window and its current lifecycle status."""

    local_date: str
    quadrant: str
    slot_index: int
    scheduled_for: str
    schedule_seed: str
    id: Optional[int] = None
    status: str = "PENDING"
    attempt_count: int = 0


def _utcnow() -> float:
    import time

    return time.time()


def _utc_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SampleStore:
    """Thread-safe SQLite access with one short-lived connection per transaction."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        os.makedirs(parent, exist_ok=True)
        self._local = threading.local()
        with self._connect() as conn:
            conn.executescript(DB_SCHEMA)
            self._migrate_samples(conn)
            self._migrate_slots(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_date_runner ON samples(local_date, runner, started_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_samples_slot ON samples(slot_id)")
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
                (str(SCHEMA_VERSION),),
            )
        self.close()

    @staticmethod
    def _migrate_samples(conn: sqlite3.Connection) -> None:
        """Add metadata columns to databases created before slot scheduling."""
        existing = {row[1] for row in conn.execute("PRAGMA table_info(samples)")}
        for name, sql_type in (
            ("slot_id", "INTEGER"),
            ("local_date", "TEXT"),
            ("quadrant", "TEXT"),
            ("failure_origin", "TEXT"),
            ("power_state", "TEXT"),
            ("gateway_reachable", "INTEGER"),
            ("external_reachable", "INTEGER"),
            ("classification_confidence", "TEXT"),
            ("evidence_json", "TEXT"),
            ("runner", "TEXT"),
            ("latency_min_ms", "REAL"),
            ("latency_max_ms", "REAL"),
            ("packet_loss_pct", "REAL"),
            ("tcp_retransmits", "INTEGER"),
        ):
            if name not in existing:
                conn.execute(f"ALTER TABLE samples ADD COLUMN {name} {sql_type}")

    @staticmethod
    def _migrate_slots(conn: sqlite3.Connection) -> None:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(measurement_slots)")}
        for name, sql_type in (
            ("classification_note", "TEXT"),
            ("classification_source", "TEXT"),
            ("classification_updated_at", "TEXT"),
        ):
            if name not in existing:
                conn.execute(f"ALTER TABLE measurement_slots ADD COLUMN {name} {sql_type}")

    # --- connection handling -------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self) -> None:
        """Close the current thread's SQLite connection, if one is open."""
        connection = getattr(self._local, "conn", None)
        if connection is not None:
            connection.close()
            del self._local.conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.close()

    # --- writes --------------------------------------------------------------
    def add_samples(self, samples: Iterable[Sample]) -> int:
        """Insert representative samples and return the number inserted."""
        added = 0
        with self._connection() as conn:
            cur = conn.cursor()
            for s in samples:
                row = s.to_row()
                cur.execute(
                    "INSERT INTO samples "
                    "(started_at, is_failure, failure_cause, failure_note, "
                    "  download_mbps, upload_mbps, ping_ms, jitter_ms, "
                    "  latency_min_ms, latency_max_ms, packet_loss_pct, tcp_retransmits, "
                    "  server_id, server_name, server_location, country, "
                    "  interface, isp, bandwidth_contracted_mbps, test_duration_sec, "
                    "  slot_id, local_date, quadrant, failure_origin, power_state, "
                    "  gateway_reachable, external_reachable, classification_confidence, "
                    "  evidence_json, runner) VALUES (" + ",".join("?" for _ in row) + ")",
                    row,
                )
                added += 1
        return added

    def add_sample(self, sample: Sample) -> int:
        """Insert one representative sample and return its database id."""
        with self._connection() as conn:
            # Claim, sample and completion must not produce duplicates after a crash.
            conn.execute("BEGIN IMMEDIATE")
            if sample.slot_id is not None:
                existing = conn.execute("SELECT id FROM samples WHERE slot_id = ? ORDER BY id LIMIT 1", (sample.slot_id,)).fetchone()
                if existing:
                    return int(existing[0])
            columns = list(sample.to_dict())
            placeholders = ",".join("?" for _ in columns)
            cur = conn.execute(
                f"INSERT INTO samples ({','.join(columns)}) VALUES ({placeholders})",
                sample.to_row(),
            )
            if sample.slot_id is not None:
                if not sample.is_failure:
                    status = "SUCCESS"
                elif sample.failure_origin == "OPERATOR":
                    status = "NO_INTERNET_OPERATOR"
                elif sample.failure_origin == "INTERNAL":
                    status = "NO_INTERNET_INTERNAL"
                elif sample.failure_cause == "power":
                    status = "POWER_OUTAGE"
                else:
                    status = "MEASUREMENT_ERROR"
                conn.execute("UPDATE measurement_slots SET status = ?, updated_at = ? WHERE id = ? AND status = 'RUNNING'", (status, _utc_from_epoch(_utcnow()), sample.slot_id))
            return int(cur.lastrowid)

    def add_attempt(self, slot_id: int, started_at: str, ended_at: str,
                    outcome: str, reason: Optional[str], metrics: dict) -> int:
        """Preserve every attempt; only selected samples enter aggregate metrics."""
        with self._connection() as conn:
            cur = conn.execute(
                "INSERT INTO measurement_attempts(slot_id, started_at, ended_at, outcome, reason, metrics_json) VALUES (?, ?, ?, ?, ?, ?)",
                (slot_id, started_at, ended_at, outcome, reason, json.dumps(metrics, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def attempts_for_slot(self, slot_id: int) -> List[dict]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM measurement_attempts WHERE slot_id = ? ORDER BY id", (slot_id,)).fetchall()
        result = [dict(row) for row in rows]
        for row in result:
            row["metrics"] = json.loads(row.pop("metrics_json"))
        return result

    def mark_attempt(self, attempt_id: int, outcome: str, reason: Optional[str] = None) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE measurement_attempts SET outcome = ?, reason = ? WHERE id = ?", (outcome, reason, attempt_id))

    def touch_slot(self, slot_id: int) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE measurement_slots SET updated_at = ? WHERE id = ? AND status = 'RUNNING'", (_utc_from_epoch(_utcnow()), slot_id))

    def recover_stale_slots(self, now_utc: str, lease_seconds: int = 300,
                            late_tolerance_seconds: int = 900) -> int:
        """Recover expired execution leases without replacing saved measurements."""
        now = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
        cutoff = (now - timedelta(seconds=lease_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        late = (now - timedelta(seconds=late_tolerance_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recovered = 0
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            slots = conn.execute("SELECT * FROM measurement_slots WHERE status = 'RUNNING' AND updated_at < ?", (cutoff,)).fetchall()
            for slot in slots:
                sample = conn.execute("SELECT is_failure, failure_origin FROM samples WHERE slot_id = ? ORDER BY id DESC LIMIT 1", (slot["id"],)).fetchone()
                if sample:
                    status = "SUCCESS" if not sample["is_failure"] else {"OPERATOR": "NO_INTERNET_OPERATOR", "INTERNAL": "NO_INTERNET_INTERNAL"}.get(sample["failure_origin"], "MEASUREMENT_ERROR")
                else:
                    status = "PENDING" if slot["scheduled_for"] >= late else "MISSED_UNKNOWN"
                conn.execute("UPDATE measurement_slots SET status = ?, updated_at = ?, classification_note = ?, classification_source = 'recovery' WHERE id = ?", (status, now_utc, "Execution lease expired; recovered after interruption", slot["id"]))
                recovered += 1
        return recovered

    # --- scheduling ---------------------------------------------------------
    def add_slots(self, slots: Iterable[MeasurementSlot]) -> int:
        """Insert planned slots idempotently and return rows newly added."""
        now = _utc_from_epoch(_utcnow())
        added = 0
        with self._connection() as conn:
            for slot in slots:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO measurement_slots "
                    "(local_date, quadrant, slot_index, scheduled_for, status, "
                    " attempt_count, schedule_seed, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'PENDING', 0, ?, ?, ?)",
                    (
                        slot.local_date,
                        slot.quadrant,
                        slot.slot_index,
                        slot.scheduled_for,
                        slot.schedule_seed,
                        now,
                        now,
                    ),
                )
                added += cur.rowcount
        return added

    def slots_for_date(self, local_date: str) -> List[dict]:
        """Return the ordered plan for one local calendar date."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM measurement_slots "
                "WHERE local_date = ? ORDER BY quadrant, slot_index",
                (local_date,),
            ).fetchall()
        return [dict(row) for row in rows]

    def all_slots(self) -> List[dict]:
        """Return all planned slots ordered by scheduled execution time."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM measurement_slots ORDER BY scheduled_for, id"
            ).fetchall()
        return [dict(row) for row in rows]

    def due_slots(self, now_utc: str) -> List[dict]:
        """Return pending slots whose scheduled UTC time has arrived."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM measurement_slots "
                "WHERE status = 'PENDING' AND scheduled_for <= ? "
                "ORDER BY scheduled_for, id",
                (now_utc,),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_slot(self, slot_id: int) -> bool:
        """Atomically move one pending slot to ``RUNNING``."""
        now = _utc_from_epoch(_utcnow())
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE measurement_slots SET status = 'RUNNING', "
                "attempt_count = attempt_count + 1, updated_at = ? "
                "WHERE id = ? AND status = 'PENDING'",
                (now, slot_id),
            )
        return cur.rowcount == 1

    def finish_slot(self, slot_id: int, status: str) -> None:
        """Persist the terminal status for a claimed slot."""
        now = _utc_from_epoch(_utcnow())
        with self._connection() as conn:
            conn.execute(
                "UPDATE measurement_slots SET status = ?, updated_at = ? "
                "WHERE id = ?",
                (status, now, slot_id),
            )

    def classify_slot(
        self,
        slot_id: int,
        status: str,
        note: Optional[str],
        source: str = "manual",
    ) -> bool:
        """Apply a manual status correction while retaining its justification."""
        now = _utc_from_epoch(_utcnow())
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE measurement_slots SET status = ?, classification_note = ?, "
                "classification_source = ?, classification_updated_at = ?, updated_at = ? "
                "WHERE id = ?",
                (status, note[:400] if note else None, source, now, now, slot_id),
            )
        return cur.rowcount == 1

    def mark_overdue_slots(self, before_utc: str) -> int:
        """Mark pending slots older than ``before_utc`` as unknown misses."""
        now = _utc_from_epoch(_utcnow())
        with self._connection() as conn:
            cur = conn.execute(
                "UPDATE measurement_slots SET status = 'MISSED_UNKNOWN', updated_at = ? "
                "WHERE status = 'PENDING' AND scheduled_for < ?",
                (now, before_utc),
            )
        return cur.rowcount

    # --- availability events -----------------------------------------------
    def add_availability_event(
        self,
        started_at: str,
        ended_at: Optional[str],
        event_type: str,
        source: str,
        confidence: str,
        note: Optional[str],
    ) -> int:
        """Persist an availability interval and reconcile overlapping slots."""
        now = _utc_from_epoch(_utcnow())
        with self._connection() as conn:
            cur = conn.execute(
                "INSERT INTO availability_events "
                "(started_at, ended_at, event_type, source, confidence, note, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (started_at, ended_at, event_type, source, confidence, note, now),
            )
            event_id = int(cur.lastrowid)
            status_by_type = {
                "POWER_OUTAGE": "POWER_OUTAGE",
                "OPERATOR_OUTAGE": "NO_INTERNET_OPERATOR",
                "INTERNAL_OUTAGE": "NO_INTERNET_INTERNAL",
            }
            slot_status = status_by_type.get(event_type)
            if slot_status:
                conn.execute(
                    "UPDATE measurement_slots SET status = ?, updated_at = ? "
                    "WHERE status IN ('PENDING', 'MISSED_UNKNOWN') "
                    "AND scheduled_for >= ? "
                    "AND (? IS NULL OR scheduled_for <= ?)",
                    (slot_status, now, started_at, ended_at, ended_at),
                )
        return event_id

    def availability_events(self) -> List[dict]:
        """Return availability intervals in chronological order."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM availability_events ORDER BY started_at, id"
            ).fetchall()
        return [dict(row) for row in rows]

    def record_heartbeat(
        self,
        service: str,
        status: str = "ok",
        metadata: Optional[dict] = None,
    ) -> None:
        """Persist the latest liveness signal for a long-running service."""
        observed_at = _utc_from_epoch(_utcnow())
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO service_heartbeats(service, observed_at, status, metadata_json) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(service) DO UPDATE SET observed_at=excluded.observed_at, "
                "status=excluded.status, metadata_json=excluded.metadata_json",
                (service, observed_at, status, metadata_json),
            )

    def latest_heartbeat(self, service: str) -> Optional[dict]:
        """Return the most recent heartbeat for a service, if present."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT service, observed_at, status, metadata_json "
                "FROM service_heartbeats WHERE service = ?",
                (service,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        try:
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            result["metadata"] = {}
            result.pop("metadata_json", None)
        return result

    def add_alert(
        self,
        kind: str,
        message: str,
        severity: str = "warning",
        sample_id: Optional[int] = None,
        payload: Optional[dict] = None,
        cooldown_seconds: int = 21600,
    ) -> Optional[int]:
        """Create a deduplicated alert and return its id, if created."""
        now_epoch = _utcnow()
        now = _utc_from_epoch(now_epoch)
        with self._connection() as conn:
            recent = conn.execute(
                "SELECT id FROM alerts WHERE kind = ? "
                "AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
                (kind, _utc_from_epoch(now_epoch - max(cooldown_seconds, 0))),
            ).fetchone()
            if recent:
                return None
            cur = conn.execute(
                "INSERT INTO alerts(created_at, kind, severity, message, sample_id, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    now,
                    kind,
                    severity,
                    message[:400],
                    sample_id,
                    json.dumps(payload or {}, sort_keys=True),
                ),
            )
            return int(cur.lastrowid)

    def mark_alert_delivery(
        self,
        alert_id: int,
        delivered: bool,
        delivery_error: Optional[str] = None,
    ) -> None:
        """Persist whether delivery of one alert succeeded or failed."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE alerts SET delivered = ?, delivery_error = ? WHERE id = ?",
                (1 if delivered else 0, delivery_error[:400] if delivery_error else None, alert_id),
            )

    def alerts(self, limit: int = 50) -> List[dict]:
        """Return the newest alerts with decoded JSON payloads."""
        limit = max(1, min(int(limit), 200))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
                item.pop("payload_json", None)
            result.append(item)
        return result

    # --- reads ---------------------------------------------------------------
    def all_samples(self, limit: Optional[int] = None, offset: int = 0) -> List[dict]:
        """Return samples ordered by timestamp, optionally paginated."""
        limit = max(1, min(int(limit), 5000)) if limit is not None else None
        offset = max(0, int(offset))
        with self._connection() as conn:
            query = "SELECT * FROM samples ORDER BY started_at ASC, id ASC"
            params: tuple[int, ...] = ()
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params = (limit, offset)
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def query_samples(self, *, runner: Optional[str] = None, local_date: Optional[str] = None,
                      from_date: Optional[str] = None, to_date: Optional[str] = None,
                      since: Optional[str] = None, quadrant: Optional[str] = None,
                      timezone_name: str = "America/Sao_Paulo", limit: Optional[int] = None,
                      offset: int = 0, descending: bool = False, max_id: Optional[int] = None) -> List[dict]:
        """Apply all filters in SQL before sorting and pagination."""
        clauses, values = [], []
        if max_id is not None:
            clauses.append("id <= ?")
            values.append(max_id)
        if runner:
            clauses.append("runner = ?")
            values.append(runner)
        if quadrant:
            clauses.append("quadrant = ?")
            values.append(quadrant)
        start, end = local_date or from_date, local_date or to_date
        if start or end:
            zone = ZoneInfo(timezone_name)
            local_parts, legacy_parts, local_values, legacy_values = [], [], [], []
            if start:
                local_parts.append("local_date >= ?")
                local_values.append(start)
                utc_start = datetime.fromisoformat(start).replace(tzinfo=zone).astimezone(timezone.utc)
                legacy_parts.append("started_at >= ?")
                legacy_values.append(utc_start.strftime("%Y-%m-%dT%H:%M:%SZ"))
            if end:
                local_parts.append("local_date <= ?")
                local_values.append(end)
                utc_end = (datetime.fromisoformat(end) + timedelta(days=1)).replace(tzinfo=zone).astimezone(timezone.utc)
                legacy_parts.append("started_at < ?")
                legacy_values.append(utc_end.strftime("%Y-%m-%dT%H:%M:%SZ"))
            clauses.append("((" + " AND ".join(local_parts) + ") OR (local_date IS NULL AND " + " AND ".join(legacy_parts) + "))")
            values.extend(local_values + legacy_values)
        if since:
            clauses.append("started_at >= ?")
            values.append(since)
        query = "SELECT * FROM samples"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        direction = "DESC" if descending else "ASC"
        query += f" ORDER BY started_at {direction}, id {direction}"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            values.extend((max(1, min(int(limit), 5000)), max(0, int(offset))))
        with self._connection() as conn:
            rows = conn.execute(query, values).fetchall()
        return [dict(row) for row in rows]

    def max_sample_id(self) -> int:
        with self._connection() as conn:
            return int(conn.execute("SELECT COALESCE(MAX(id), 0) FROM samples").fetchone()[0])

    def samples_since(
        self,
        started_at: str,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[dict]:
        """Return samples with started_at >= given UTC ISO string."""
        limit = max(1, min(int(limit), 5000)) if limit is not None else None
        offset = max(0, int(offset))
        with self._connection() as conn:
            query = "SELECT * FROM samples WHERE started_at >= ? ORDER BY started_at ASC"
            params: tuple = (started_at,)
            if limit is not None:
                query += " LIMIT ? OFFSET ?"
                params += (limit, offset)
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def samples_last_minutes(
        self,
        minutes: int,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[dict]:
        """Return samples newer than a relative UTC time cutoff."""
        cutoff = _utcnow() - minutes * 60
        return self.samples_since(_utc_from_epoch(cutoff), limit=limit, offset=offset)

    def latest(self) -> Optional[dict]:
        """Return the newest persisted sample, if any."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM samples ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def consecutive_external_failure_count(self, runner: Optional[str]) -> int:
        """Count the current consecutive external-outage observations.

        The sequence is persisted in ``samples`` and resets after any success,
        internal failure, measurement failure, or different runner. Both the
        initial external probe and a timeout followed by an external probe
        failure contribute to the same outage streak.
        """
        causes = ("external_unreachable", "external_timeout")
        query = (
            "SELECT is_failure, failure_cause, runner FROM samples "
            "ORDER BY started_at DESC, id DESC"
        )
        with self._connection() as conn:
            rows = conn.execute(query).fetchall()
        count = 0
        for row in rows:
            if (
                not row[0]
                or row[1] not in causes
                or row[2] != runner
            ):
                break
            count += 1
        return count

    def count(self) -> int:
        """Return the number of persisted sample rows."""
        with self._connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]

    def reset(self) -> int:
        """Delete all measurement history and alerts; returns rows deleted."""
        # VACUUM cannot run inside an explicit transaction, so we commit the
        # DELETE (which opens a transaction via the context manager) before
        # issuing it on the raw connection.
        with self._connection() as conn:
            n = conn.execute("DELETE FROM samples").rowcount
            n += conn.execute("DELETE FROM measurement_slots").rowcount
            n += conn.execute("DELETE FROM availability_events").rowcount
            n += conn.execute("DELETE FROM alerts").rowcount
            n += conn.execute("DELETE FROM measurement_attempts").rowcount
        with self._connection() as conn:
            conn.execute("VACUUM")
        return n
