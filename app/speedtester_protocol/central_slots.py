# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Wire-stable central plan; no dependency on a language runtime's PRNG."""
from datetime import datetime, time, timedelta, timezone
import hashlib
import hmac
from zoneinfo import ZoneInfo
from functools import lru_cache
from importlib.resources import files
from .quadrants import QUADRANTS, PlannedSlot, SLOT_END_MARGIN_SECONDS, MIN_SLOT_GAP_SECONDS


TIMEZONE_DATABASE = '2026.5'


@lru_cache(maxsize=256)
def central_zone(name):
    # OS tzdb revisions differ across native platforms. The protocol uses the
    # same pinned tzdata package on both sides, with no host-db fallback.
    import tzdata
    if tzdata.__version__ != TIMEZONE_DATABASE:
        raise ValueError('unsupported timezone database')
    if not isinstance(name,str) or not name or any(part in {'','..','.'} for part in name.split('/')) or name.startswith('/'):
        raise ValueError('invalid timezone')
    try:
        with files('tzdata.zoneinfo').joinpath(*name.split('/')).open('rb') as source:
            return ZoneInfo.from_file(source,key=name)
    except (OSError, ValueError) as exc:
        raise ValueError('unknown timezone') from exc


def _central_offsets(day, quadrant, key, available):
    offsets = []
    for counter in range(10000):
        message = f'{day.isoformat()}:{quadrant}:{counter}'.encode('utf-8')
        candidate = int.from_bytes(hmac.new(key, message, hashlib.sha256).digest(), 'big') % (available + 1)
        if all(abs(candidate - old) >= MIN_SLOT_GAP_SECONDS for old in offsets):
            offsets.append(candidate)
        if len(offsets) == 2:
            return sorted(offsets)
    raise ValueError('could not plan spaced central slots')


def plan_central_day_slots(day, timezone_name, seed):
    """v1: HMAC-SHA256 offsets, UTF-8 date:period:counter, big endian modulo."""
    key=bytes.fromhex(seed)
    if len(key)!=32:
        raise ValueError('invalid central seed')
    zone=central_zone(timezone_name)
    planned=[]
    for quadrant,start_time,end_time in QUADRANTS:
        start=datetime.combine(day,start_time,zone).astimezone(timezone.utc)
        end=datetime.combine(day+timedelta(days=1),time(),zone) if quadrant=='noite' else datetime.combine(day,end_time,zone)
        end=end.astimezone(timezone.utc)
        available=int((end-start).total_seconds())-30-SLOT_END_MARGIN_SECONDS
        if available<MIN_SLOT_GAP_SECONDS:
            raise ValueError('quadrant too short')
        for index,offset in enumerate(_central_offsets(day, quadrant, key, available),start=1):
            planned.append(PlannedSlot(day.isoformat(),quadrant,index,(start+timedelta(seconds=offset)).strftime('%Y-%m-%dT%H:%M:%SZ'),seed))
    return planned
