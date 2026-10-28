# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Independent schedules retain durable history and never move claimed slots."""
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from api.store import MeasurementSlot, SampleStore
from collector.collector import Collector
from collector.quadrants import DEFAULT_SCHEDULE_SEED, local_date_now, plan_day_slots


class IndependentScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = SimpleNamespace(timezone='America/Sao_Paulo',
                                        measurements_per_quadrant=2, sample_duration_seconds=30)
        self.day = local_date_now(self.settings.timezone) + timedelta(days=1)

    def store(self, name):
        store = SampleStore(str(self.root / name))
        self.addCleanup(store.close)
        return store

    def test_distinct_databases_schedule_independently_and_survive_restart(self):
        first, second = self.store('first.db'), self.store('second.db')
        with patch('api.store.secrets.token_hex', side_effect=['a' * 32, 'b' * 32, 'c' * 32]):
            Collector(self.settings, first)._ensure_schedule(self.day)
            Collector(self.settings, second)._ensure_schedule(self.day)
            before = first.slots_for_date(self.day.isoformat())
            Collector(self.settings, first)._ensure_schedule(self.day)
        other = second.slots_for_date(self.day.isoformat())
        self.assertEqual(before, first.slots_for_date(self.day.isoformat()))
        self.assertNotEqual([row['scheduled_for'] for row in before],
                            [row['scheduled_for'] for row in other])
        self.assertEqual({row['schedule_seed'] for row in before}, {'a' * 32})
        self.assertEqual({row['schedule_seed'] for row in other}, {'b' * 32})
        first.close()
        reopened = self.store('first.db')
        self.assertEqual(reopened.local_schedule_seed(), 'a' * 32)

    def test_upgrade_replans_only_unstarted_future_legacy_slots(self):
        store = self.store('upgrade.db')
        legacy = plan_day_slots(self.day, self.settings.timezone)
        store.add_slots(MeasurementSlot(s.local_date, s.quadrant, s.slot_index,
                                        s.scheduled_for, s.schedule_seed) for s in legacy)
        before = store.slots_for_date(self.day.isoformat())
        preserved = before[0]
        self.assertTrue(store.claim_slot(preserved['id']))
        store.add_attempt(before[1]['id'], '2030-01-01T00:00:00Z', '2030-01-01T00:00:01Z',
                          'error', 'fixture', {})
        with patch('api.store.secrets.token_hex', return_value='a' * 32):
            collector = Collector(self.settings, store)
            collector._ensure_schedule(self.day)
            first = store.slots_for_date(self.day.isoformat())
            collector._ensure_schedule(self.day)
        after = store.slots_for_date(self.day.isoformat())
        self.assertEqual(first, after)
        by_id = {row['id']: row for row in after}
        self.assertEqual(by_id[preserved['id']]['scheduled_for'], preserved['scheduled_for'])
        self.assertEqual(by_id[preserved['id']]['status'], 'RUNNING')
        self.assertEqual(by_id[before[1]['id']]['scheduled_for'], before[1]['scheduled_for'])
        for old in before[2:]:
            current = by_id[old['id']]
            self.assertNotEqual(current['schedule_seed'], DEFAULT_SCHEDULE_SEED)
            self.assertNotEqual(current['scheduled_for'], old['scheduled_for'])
            self.assertEqual(current['status'], 'PENDING')
        self.assertEqual(len(after), 8)

    def test_due_and_completed_slots_are_never_moved(self):
        store = self.store('history.db')
        slots = [
            MeasurementSlot('2030-01-01', 'manha', 1, '2030-01-01T09:00:00Z', DEFAULT_SCHEDULE_SEED),
            MeasurementSlot('2030-01-01', 'manha', 2, '2030-01-01T11:00:00Z', DEFAULT_SCHEDULE_SEED),
        ]
        store.add_slots(slots)
        rows = store.slots_for_date('2030-01-01')
        proposal = [[
            MeasurementSlot('2030-01-01', 'manha', 1, '2030-01-01T10:15:00Z', 'new'),
            MeasurementSlot('2030-01-01', 'manha', 2, '2030-01-01T12:00:00Z', 'new'),
        ]]
        self.assertEqual(store.migrate_legacy_future_slots('2030-01-01', proposal,
                         '2030-01-01T10:00:00Z', DEFAULT_SCHEDULE_SEED), 1)
        after = {row['id']: row for row in store.slots_for_date('2030-01-01')}
        self.assertEqual(after[rows[0]['id']]['scheduled_for'], rows[0]['scheduled_for'])
        self.assertEqual(after[rows[1]['id']]['scheduled_for'], '2030-01-01T12:00:00Z')

    def test_unsafe_proposals_leave_future_slots_unchanged(self):
        store = self.store('unsafe.db')
        old = MeasurementSlot('2030-01-01', 'manha', 1, '2030-01-01T11:00:00Z', DEFAULT_SCHEDULE_SEED)
        store.add_slots([old])
        before = store.slots_for_date('2030-01-01')
        close = MeasurementSlot('2030-01-01', 'manha', 1, '2030-01-01T11:05:00Z', 'new')
        past = MeasurementSlot('2030-01-01', 'manha', 1, '2030-01-01T09:00:00Z', 'new')
        moved = store.migrate_legacy_future_slots('2030-01-01', [[close], [past]],
                                                 '2030-01-01T10:00:00Z', DEFAULT_SCHEDULE_SEED)
        self.assertEqual(moved, 0)
        self.assertEqual(store.slots_for_date('2030-01-01'), before)


if __name__ == '__main__':
    unittest.main()
