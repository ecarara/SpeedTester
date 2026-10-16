# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Daily scheduling regressions use a logical clock and never invoke a runner."""
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo
from speedtester_protocol.installation import protected_queue
from speedtester_protocol.schedule import DailySchedule, migrate_installation
from speedtester_protocol.quadrants import plan_day_slots, quadrant_for_timestamp


def epoch(value):
    return int(datetime.fromisoformat(value).timestamp())


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.queue=protected_queue(Path(self.temp.name).resolve()/'state')
        self.policy={'format':'quadrants-v1','timezone':'America/Sao_Paulo','seed':'a'*32}
        self.schedule=DailySchedule(self.queue,self.policy)
        self.base=epoch('2026-10-14T22:00:00+00:00')
        self.days=self.schedule.refresh(self.base,activate=True)
        self.slots=self.days[1]['slots']

    def test_shared_planner_has_eight_spaced_slots_in_each_local_day_and_dst(self):
        from collector.quadrants import plan_day_slots as standalone
        self.assertIs(standalone,plan_day_slots)
        for zone,day in [('America/Sao_Paulo',date(2026,10,15)),('Europe/Madrid',date(2026,3,29)),
                ('Europe/Madrid',date(2026,10,25)),('Pacific/Auckland',date(2026,9,27))]:
            slots=plan_day_slots(day,zone,schedule_seed='a'*32)
            self.assertEqual(slots,plan_day_slots(day,zone,schedule_seed='a'*32))
            self.assertEqual(Counter(s.quadrant for s in slots),{'madrugada':2,'manha':2,'tarde':2,'noite':2})
            self.assertEqual(len({s.scheduled_for for s in slots}),8)
            previous={}
            for slot in slots:
                at=datetime.fromisoformat(slot.scheduled_for.replace('Z','+00:00'))
                self.assertEqual(at.astimezone(ZoneInfo(zone)).date(),day)
                self.assertEqual(quadrant_for_timestamp(at,zone),slot.quadrant)
                if slot.quadrant in previous:self.assertGreaterEqual((at-previous[slot.quadrant]).total_seconds(),3600)
                previous[slot.quadrant]=at

    def test_full_day_has_exactly_eight_claims_with_restart_after_each_one(self):
        claims=[]
        for slot in self.slots:
            self.schedule=DailySchedule(protected_queue(self.queue.directory),self.policy)
            claimed=self.schedule.claim(slot['at'],'synthetic:grant_request')
            self.assertIsNotNone(claimed)
            self.assertEqual(self.queue.state('synthetic:grant_request'),claimed['request_id'])
            claims.append(claimed)
            self.schedule.finish(claimed,attempt_id='synthetic-attempt')
            self.assertIsNone(self.schedule.claim(slot['at'],'synthetic:grant_request'))
        self.assertEqual(Counter(s['quadrant'] for s in claims),{'madrugada':2,'manha':2,'tarde':2,'noite':2})
        self.assertEqual(len({s['request_id'] for s in claims}),8)
        self.assertGreater(self.queue.state('next_due'),self.slots[-1]['at'])

    def test_reservation_survives_crash_and_is_never_claimed_again(self):
        first=self.slots[0]
        self.assertIsNone(self.schedule.claim(first['at']-1,'synthetic:grant_request'))
        self.assertIsNotNone(self.schedule.claim(first['at'],'synthetic:grant_request'))
        reopened=DailySchedule(protected_queue(self.queue.directory),self.policy)
        self.assertIsNone(reopened.claim(first['at']+1,'synthetic:grant_request'))
        day=self.queue.state('schedule:day:'+self.days[1]['date'])
        self.assertEqual(day['slots'][0]['state'],'interrupted')
        self.assertIsNotNone(reopened.claim(self.slots[1]['at'],'synthetic:grant_request'))

    def test_activation_never_runs_now_or_catches_up_missed_slots(self):
        first=self.slots[0]
        before=[s['at'] for s in self.slots]
        self.schedule.refresh(first['at']+1,activate=True)
        self.assertIsNone(self.schedule.claim(first['at']+1,'synthetic:grant_request'))
        day=self.queue.state('schedule:day:'+self.days[1]['date'])
        self.assertEqual([s['at'] for s in day['slots']],before)
        self.assertEqual(day['slots'][0]['state'],'skipped')
        self.assertIsNotNone(self.schedule.claim(self.slots[1]['at'],'synthetic:grant_request'))

    def test_sleep_and_quadrant_end_skip_old_slots_without_compensation(self):
        last=self.slots[-1]
        self.assertIsNone(self.schedule.claim(last['deadline']+1,'synthetic:grant_request'))
        day=self.queue.state('schedule:day:'+self.days[1]['date'])
        self.assertTrue(all(s['state']=='missed' for s in day['slots']))
        tomorrow=epoch('2026-10-16T13:00:00+00:00')
        records=self.schedule.refresh(tomorrow)
        self.assertEqual(records[0]['date'],'2026-10-16')
        self.assertEqual(len(records[0]['slots']),8)

    def test_old_next_due_cache_cannot_trigger_an_unscheduled_test(self):
        self.queue.state('next_due',1)
        self.assertIsNone(self.schedule.claim(self.base,'synthetic:grant_request'))
        self.assertGreater(self.queue.state('next_due'),self.base)

    def test_clock_rollback_never_reopens_previously_consumed_slots(self):
        second=self.slots[1]
        claim=self.schedule.claim(second['at'],'synthetic:grant_request')
        self.schedule.finish(claim,attempt_id='synthetic')
        self.assertIsNone(self.schedule.claim(self.slots[0]['at'],'synthetic:grant_request'))
        self.assertIsNone(self.schedule.claim(second['at'],'synthetic:grant_request'))

    def test_legacy_migration_preserves_identity_queue_and_ignores_interval(self):
        from speedtester_protocol.models import Profile
        from test_desktop_client import configuration
        original={'origin':'https://server.example','profile':Profile.model_validate(configuration()['profile']).model_dump(),'interval':3600,
            'possession_private':'synthetic-key','measurement_private':'synthetic-key-2'}
        self.queue.state('installation',original)
        migrated,changed=migrate_installation(self.queue,original,'America/Sao_Paulo')
        self.assertTrue(changed);self.assertNotIn('interval',migrated)
        for key,value in original.items():
            if key!='interval':self.assertEqual(migrated[key],value)
        self.assertEqual(migrate_installation(self.queue,migrated),(migrated,False))
        broken={**migrated,'schedule':{'format':'unknown'}}
        with self.assertRaises(ValueError):migrate_installation(self.queue,broken)

    def test_a_changed_policy_cannot_reset_existing_day_quotas(self):
        changed={**self.policy,'timezone':'UTC'}
        with self.assertRaises(ValueError):DailySchedule(self.queue,changed).refresh(self.base)


if __name__=='__main__':unittest.main()
