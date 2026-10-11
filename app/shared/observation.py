# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Summarize observation evidence without publishing the destination address."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
import statistics


def start_observation(store, settings):
    fingerprint = hashlib.sha256(f'{settings.speedtest_runner}:{settings.iperf3_server}:{settings.iperf3_port}'.encode()).hexdigest()
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT value FROM schema_meta WHERE key='observation'").fetchone()
        previous = json.loads(row[0]) if row else {}
        if previous.get('target_fingerprint') != fingerprint:
            value = {'started_at': datetime.now(timezone.utc).isoformat(), 'target_fingerprint': fingerprint}
            conn.execute("INSERT OR REPLACE INTO schema_meta VALUES ('observation',?)", (json.dumps(value),))


def report(store, settings, days=14, now=None):
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    with store._connection() as conn:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='observation'").fetchone()
        baseline = json.loads(row[0]) if row else {}
        if baseline.get('started_at'):
            since = max(since, datetime.fromisoformat(baseline['started_at']))
        since_text = since.strftime('%Y-%m-%dT%H:%M:%SZ')
        until_text = now.strftime('%Y-%m-%dT%H:%M:%SZ')
        samples = conn.execute('SELECT * FROM samples WHERE started_at>=? AND started_at<=?', (since_text, until_text)).fetchall()
        slots = conn.execute('SELECT status FROM measurement_slots WHERE scheduled_for>=? AND scheduled_for<=?', (since_text, until_text)).fetchall()
        attempts = conn.execute('SELECT outcome,metrics_json FROM measurement_attempts WHERE started_at>=? AND started_at<=?', (since_text, until_text)).fetchall()
    good = [row['download_mbps'] for row in samples if not row['is_failure'] and row['download_mbps'] is not None]
    states = Counter(row['status'] for row in slots)
    metrics = [json.loads(row['metrics_json']) for row in attempts]
    known = [item['transfer_bytes'] for item in metrics if item.get('transfer_bytes') is not None]
    return {'from': since.isoformat(), 'to': now.isoformat(), 'observation_started_at': baseline.get('started_at'),
        'observed_days': round((now-since).total_seconds()/86400, 2), 'requested_days': days,
        'target_controlled': settings.measurement_target_controlled, 'sla_evidence': False,
        'limitation': 'Medições até um destino; não constituem comprovação de SLA.',
        'samples': len(samples), 'successes': len(good), 'failures': sum(row['is_failure'] for row in samples),
        'due_slots': len(slots), 'slot_states': dict(states),
        'completion_pct': round(states['SUCCESS']/len(slots)*100, 1) if slots else None,
        'attempt_outcomes': dict(Counter(row['outcome'] for row in attempts)),
        'known_transfer_bytes': sum(known), 'unknown_transfer_attempts': len(attempts)-len(known),
        'download_median_mbps': statistics.median(good) if good else None,
        'download_p10_mbps': percentile(good, .1), 'download_p95_mbps': percentile(good, .95)}


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered)-1)*fraction
    lower = int(position)
    upper = min(lower+1, len(ordered)-1)
    return ordered[lower]+(ordered[upper]-ordered[lower])*(position-lower)
