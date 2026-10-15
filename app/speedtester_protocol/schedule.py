# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Durable eight-slot local-day schedule. No network, probes or catch-up tests."""
from datetime import datetime, timedelta, timezone
import secrets
from uuid import uuid4
from zoneinfo import ZoneInfo
from .quadrants import plan_day_slots, quadrant_for_timestamp, SLOT_END_MARGIN_SECONDS

FORMAT = 'quadrants-v1'
HEADER = 'schedule:cursor'
GRACE_SECONDS = 600
TEST_SECONDS = 30


def local_timezone():
    from tzlocal import get_localzone_name
    value = get_localzone_name()
    ZoneInfo(value)
    return value


def policy(timezone_name=None):
    return {'format': FORMAT, 'timezone': timezone_name or local_timezone(), 'seed': secrets.token_hex(16)}


def migrate_installation(queue, config, timezone_name=None):
    """Discard the old interval cache; preserve keys, tokens, profile and queue."""
    if 'schedule' in config:
        DailySchedule(queue, config['schedule'])
        return config, False
    migrated = {key: value for key, value in config.items() if key != 'interval'}
    migrated['schedule'] = policy(timezone_name)
    queue.state('installation', migrated)
    return migrated, True


class DailySchedule:
    def __init__(self, queue, configuration):
        self.queue, self.policy = queue, configuration
        if set(configuration) != {'format', 'timezone', 'seed'} or configuration['format'] != FORMAT:
            raise ValueError('invalid_schedule_policy')
        if not isinstance(configuration['seed'], str) or not 16 <= len(configuration['seed']) <= 64:
            raise ValueError('invalid_schedule_seed')
        self.zone = ZoneInfo(configuration['timezone'])

    def _save(self, conn, key, value):
        if self.queue._read_state(conn,key) != value:
            self.queue._write_state(conn,key,value)

    @staticmethod
    def key(day):
        return 'schedule:day:' + day.isoformat()

    def _day(self, conn, day, floor):
        stored = self.queue._read_state(conn, self.key(day))
        if stored is not None:
            return stored
        slots = []
        for item in plan_day_slots(day, self.policy['timezone'], schedule_seed=self.policy['seed']):
            at = int(datetime.fromisoformat(item.scheduled_for.replace('Z', '+00:00')).timestamp())
            end_hour = {'madrugada': 6, 'manha': 12, 'tarde': 18, 'noite': 24}[item.quadrant]
            end_day = day + timedelta(days=1) if end_hour == 24 else day
            end = datetime.combine(end_day, datetime.min.time(), self.zone).replace(hour=end_hour % 24)
            deadline = min(at + GRACE_SECONDS, int(end.timestamp()) - TEST_SECONDS - SLOT_END_MARGIN_SECONDS)
            slots.append({'quadrant': item.quadrant, 'index': item.slot_index, 'at': at,
                'deadline': deadline, 'end_at': int(end.timestamp()), 'state': 'pending' if at >= floor else 'skipped'})
        result = {'date': day.isoformat(), 'timezone': self.policy['timezone'], 'seed': self.policy['seed'], 'slots': slots}
        self._save(conn, self.key(day), result)
        return result

    def _refresh(self, conn, now, activate=False):
        header = self.queue._read_state(conn, HEADER)
        if header is None:
            header = {'policy': self.policy, 'not_before': now + 60, 'last_now': now, 'last_day': None}
        if header['policy'] != self.policy:
            raise ValueError('schedule_policy_changed')
        if activate:
            header['not_before'] = max(header['not_before'], now + 60)
        effective = max(now, header['last_now'])
        today = datetime.fromtimestamp(effective, self.zone).date()
        # Classify only previously materialized days; never run a missed backlog.
        if header['last_day']:
            previous = datetime.fromisoformat(header['last_day']).date()
            for day in {previous, previous + timedelta(days=1)}:
                if day >= today:
                    continue
                record = self.queue._read_state(conn, self.key(day))
                if record:
                    for slot in record['slots']:
                        if slot['state'] in {'pending', 'claimed'}:
                            slot['state'] = 'interrupted' if slot['state'] == 'claimed' else 'missed'
                    self._save(conn, self.key(day), record)
        days = []
        quadrant = quadrant_for_timestamp(datetime.fromtimestamp(effective, timezone.utc), self.policy['timezone'])
        for day in (today, today + timedelta(days=1)):
            record = self._day(conn, day, header['not_before'])
            for slot in record['slots']:
                if slot['state'] == 'claimed':
                    slot['state'] = 'interrupted'
                elif slot['state'] == 'pending':
                    if slot['at'] < header['not_before']:
                        slot['state'] = 'skipped'
                    elif slot['deadline'] < effective or (day == today and slot['at'] <= effective and slot['quadrant'] != quadrant):
                        slot['state'] = 'missed'
            self._save(conn, self.key(day), record)
            days.append(record)
        header.update(last_now=effective, last_day=today.isoformat())
        self._save(conn, HEADER, header)
        pending = [slot['at'] for day in days for slot in day['slots'] if slot['state'] == 'pending']
        self._save(conn, 'next_due', min(pending) if pending else None)
        return header, days

    def refresh(self, now, *, activate=False):
        with self.queue.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            _, days = self._refresh(conn, int(now), activate)
            return days

    def claim(self, now, request_key):
        now = int(now)
        with self.queue.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            header, days = self._refresh(conn, now)
            if now < header['last_now']:
                return None
            for day in days:
                for slot in day['slots']:
                    if slot['state'] == 'pending' and slot['at'] <= now <= slot['deadline']:
                        # Reservation and grant identity commit before any request/runner.
                        slot.update(state='claimed', request_id=str(uuid4()))
                        self._save(conn, request_key, slot['request_id'])
                        self._save(conn, self.key(datetime.fromisoformat(day['date']).date()), day)
                        pending = [s['at'] for d in days for s in d['slots'] if s['state'] == 'pending']
                        self._save(conn, 'next_due', min(pending) if pending else None)
                        return {**slot, 'date': day['date']}
        return None

    def finish(self, slot, *, attempt_id=None):
        with self.queue.connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            key = 'schedule:day:' + slot['date']
            day = self.queue._read_state(conn, key)
            original = next(s for s in day['slots'] if s['quadrant'] == slot['quadrant'] and s['index'] == slot['index'])
            if original.get('request_id') != slot['request_id']:
                raise ValueError('schedule_claim_changed')
            original.update(state='attempted' if attempt_id else 'failed', attempt_id=attempt_id)
            self._save(conn, key, day)
