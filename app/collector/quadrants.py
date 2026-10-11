# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Daily measurement slots divided into four local-time quadrants."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


QUADRANTS: tuple[tuple[str, time, time], ...] = (
    ("madrugada", time(0, 0), time(6, 0)),
    ("manha", time(6, 0), time(12, 0)),
    ("tarde", time(12, 0), time(18, 0)),
    ("noite", time(18, 0), time(23, 59, 59)),
)
DEFAULT_SCHEDULE_SEED = "speedtester-v1"
SLOT_END_MARGIN_SECONDS = 60
MIN_SLOT_GAP_SECONDS = 60 * 60


@dataclass(frozen=True)
class PlannedSlot:
    """One deterministic expected measurement in local-day coordinates."""

    local_date: str
    quadrant: str
    slot_index: int
    scheduled_for: str
    schedule_seed: str


def local_date_now(tz_name: str, now: datetime | None = None) -> date:
    """Return the current date in the configured operational timezone."""
    zone = ZoneInfo(tz_name)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(zone).date()


def plan_day_slots(
    local_day: date,
    tz_name: str,
    count_per_quadrant: int = 2,
    test_duration_seconds: int = 30,
    schedule_seed: str = DEFAULT_SCHEDULE_SEED,
) -> list[PlannedSlot]:
    """Create deterministic random slots for one local calendar day.

    The seed is recorded with every slot. Re-running this function for the same
    date and configuration returns the same schedule, which prevents a process
    restart from moving already planned measurements.
    """
    if count_per_quadrant < 1:
        raise ValueError("count_per_quadrant must be positive")
    if test_duration_seconds < 0:
        raise ValueError("test_duration_seconds cannot be negative")

    zone = ZoneInfo(tz_name)
    planned: list[PlannedSlot] = []
    for quadrant, start_time, end_time in QUADRANTS:
        start = datetime.combine(local_day, start_time, tzinfo=zone)
        if quadrant == "noite":
            end = datetime.combine(local_day + timedelta(days=1), time(0, 0), tzinfo=zone)
        else:
            end = datetime.combine(local_day, end_time, tzinfo=zone)
        latest = end - timedelta(seconds=test_duration_seconds + SLOT_END_MARGIN_SECONDS)
        available = int((latest - start).total_seconds())
        required = (count_per_quadrant - 1) * MIN_SLOT_GAP_SECONDS
        if available < required:
            raise ValueError(f"quadrant {quadrant} is too short for requested slots")

        rng = random.Random(f"{schedule_seed}:{local_day.isoformat()}:{quadrant}")
        offsets: list[int] = []
        attempts = 0
        while len(offsets) < count_per_quadrant and attempts < 10_000:
            candidate = rng.randint(0, available)
            if all(abs(candidate - current) >= MIN_SLOT_GAP_SECONDS for current in offsets):
                offsets.append(candidate)
            attempts += 1
        if len(offsets) != count_per_quadrant:
            raise ValueError(f"could not create spaced slots for quadrant {quadrant}")

        for index, offset in enumerate(sorted(offsets), start=1):
            scheduled = start + timedelta(seconds=offset)
            planned.append(
                PlannedSlot(
                    local_date=local_day.isoformat(),
                    quadrant=quadrant,
                    slot_index=index,
                    scheduled_for=scheduled.astimezone(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    schedule_seed=schedule_seed,
                )
            )
    return planned


def quadrant_for_timestamp(timestamp: datetime, tz_name: str) -> str:
    """Resolve a UTC or aware timestamp to the configured local quadrant."""
    zone = ZoneInfo(tz_name)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    local_time = timestamp.astimezone(zone).time()
    for quadrant, start, end in QUADRANTS:
        if start <= local_time < end or quadrant == "noite" and local_time >= start:
            return quadrant
    return "madrugada"
