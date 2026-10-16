# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Wire-stable central plan; no dependency on a language runtime's PRNG."""
from datetime import datetime, time, timedelta, timezone
import hashlib
import hmac
from zoneinfo import ZoneInfo
from .quadrants import QUADRANTS, PlannedSlot, SLOT_END_MARGIN_SECONDS, MIN_SLOT_GAP_SECONDS


def plan_central_day_slots(day, timezone_name, seed):
    """v1: HMAC-SHA256 offsets, UTF-8 date:period:counter, big endian modulo."""
    key=bytes.fromhex(seed)
    if len(key)!=32:
        raise ValueError('invalid central seed')
    zone=ZoneInfo(timezone_name)
    planned=[]
    for quadrant,start_time,end_time in QUADRANTS:
        start=datetime.combine(day,start_time,zone).astimezone(timezone.utc)
        end=datetime.combine(day+timedelta(days=1),time(),zone) if quadrant=='noite' else datetime.combine(day,end_time,zone)
        end=end.astimezone(timezone.utc)
        available=int((end-start).total_seconds())-30-SLOT_END_MARGIN_SECONDS
        if available<MIN_SLOT_GAP_SECONDS:
            raise ValueError('quadrant too short')
        offsets=[]
        for counter in range(10000):
            message=f'{day.isoformat()}:{quadrant}:{counter}'.encode('utf-8')
            candidate=int.from_bytes(hmac.new(key,message,hashlib.sha256).digest(),'big')%(available+1)
            if all(abs(candidate-old)>=MIN_SLOT_GAP_SECONDS for old in offsets):
                offsets.append(candidate)
            if len(offsets)==2:
                break
        if len(offsets)!=2:
            raise ValueError('could not plan spaced central slots')
        for index,offset in enumerate(sorted(offsets),start=1):
            planned.append(PlannedSlot(day.isoformat(),quadrant,index,(start+timedelta(seconds=offset)).strftime('%Y-%m-%dT%H:%M:%SZ'),seed))
    return planned
