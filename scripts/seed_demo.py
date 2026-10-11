#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Create a new SQLite database with synthetic data; never run a speed test."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from api.store import MeasurementSlot, Sample, SampleStore
from collector.quadrants import plan_day_slots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="New database path")
    parser.add_argument("--date", type=date.fromisoformat, default=date(2026, 10, 10))
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against overwriting an existing symlink.
    with args.db.open("xb"):
        pass
    store = SampleStore(str(args.db))
    for day_index in range(7):
        day = args.date - timedelta(days=6 - day_index)
        store.add_slots(
            MeasurementSlot(**asdict(slot))
            for slot in plan_day_slots(day, "America/Sao_Paulo", schedule_seed="public-demo")
        )
        slots = sorted(store.slots_for_date(day.isoformat()), key=lambda slot: slot["scheduled_for"])
        for index, slot in enumerate(slots):
            download = [925, 941, 918, 936, 902, 948, 933, 942][index] - (6 - day_index) * 3
            store.add_sample(Sample(
                started_at=slot["scheduled_for"], local_date=day.isoformat(),
                quadrant=slot["quadrant"], slot_id=slot["id"], runner="iperf3",
                download_mbps=download, upload_mbps=460 + index * 4,
                ping_ms=5.2 + index * 0.2, jitter_ms=0.4 + index * 0.05,
                latency_min_ms=4.8, latency_max_ms=7.5, packet_loss_pct=0,
                tcp_retransmits=index % 3, bandwidth_contracted_mbps=1000,
                server_name="iperf3.example.com", isp="Operadora de demonstração",
                interface="eth0", test_duration_sec=20,
            ))
            store.finish_slot(slot["id"], "SUCCESS")
    start = datetime.combine(args.date - timedelta(days=1), datetime.min.time(),
                             tzinfo=ZoneInfo("America/Sao_Paulo")) + timedelta(hours=19)
    store.add_availability_event(
        start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        (start + timedelta(minutes=8)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "INTERNAL_OUTAGE", "demo", "high", "Evento fictício: reinício do roteador de demonstração",
    )
    # A one-time synthetic heartbeat; it will naturally become stale later.
    store.record_heartbeat("collector", "idle", {"demo": True})
    print(f"Demo created: {args.db} (56 synthetic samples, no network measurements)")


if __name__ == "__main__":
    main()
