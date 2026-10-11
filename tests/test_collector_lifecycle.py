# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Test the real schedule loop and incident classification without network I/O."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from fixtures import IntegrationFixture
from api.store import MeasurementSlot
from collector.collector import Collector, ConnectivityFailure
from collector.connectivity import ConnectivitySnapshot
from collector.iperf3_runner import Iperf3Timeout


class CollectorLifecycleTests(IntegrationFixture):
    def test_loop_claims_persists_recovers_and_stops_with_heartbeat(self):
        now=datetime.now(timezone.utc)
        self.store.add_slots([MeasurementSlot(now.date().isoformat(),'manha',1,(now-timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),'fixture')])
        collector=Collector(self.settings,self.store)
        unavailable=ConnectivitySnapshot(None,False,False,{'test':True})
        with patch.object(collector,'_ensure_schedule'),patch('collector.collector.probe_connectivity',return_value=unavailable),patch('collector.collector.time.sleep',side_effect=lambda _:collector._handle_signal(15,None)):
            collector.run_forever()
        self.assertEqual(self.store.count(),1)
        self.assertEqual(self.store.all_samples()[0]['failure_origin'],'INTERNAL')
        self.assertEqual(self.store.latest_heartbeat('collector')['status'],'stopped')
        collector._ensure_schedule(now.date())
        collector._ensure_schedule((now+timedelta(days=1)).date())
        self.assertGreaterEqual(len(self.store.all_slots()),16)

    def test_external_failures_become_operator_only_after_three_and_keep_origin(self):
        collector=Collector(self.settings,self.store)
        unavailable=ConnectivitySnapshot('192.0.2.1',True,False,{'test':True})
        for index in range(3):
            slot=self.slot(f'2026-10-11T{12+index}:00:00Z') if index==0 else {'id':100+index,'local_date':'2026-10-11','quadrant':'manha'}
            with patch('collector.collector.probe_connectivity',return_value=unavailable):
                sample=collector._run_single(slot)
            self.assertEqual(sample.failure_origin,'OPERATOR' if index==2 else 'UNKNOWN')
        self.assertEqual(self.store.alerts()[0]['kind'],'operator_outage')

    def test_runner_errors_stay_measurement_errors_and_second_timeout_is_bounded(self):
        collector=Collector(self.settings,self.store);slot=self.slot();self.store.claim_slot(slot['id'])
        available=ConnectivitySnapshot('192.0.2.1',True,True,{'test':True})
        with patch('collector.collector.probe_connectivity',return_value=available),patch.object(collector,'_dispatch_speedtest',side_effect=RuntimeError('server returned invalid data')):
            sample=collector._run_single(slot)
        self.assertEqual(sample.failure_origin,'MEASUREMENT')
        self.assertEqual(self.store.all_slots()[0]['status'],'MEASUREMENT_ERROR')
        with patch('collector.collector.probe_connectivity',return_value=available),patch.object(collector,'_execute_speedtest',side_effect=Iperf3Timeout('timeout')) as execute:
            with self.assertRaises(Iperf3Timeout):collector._execute_speedtest_with_timeout_recovery()
        self.assertEqual(execute.call_count,2)
        with patch('collector.collector.probe_connectivity',return_value=ConnectivitySnapshot(None,False,False,{})):
            with self.assertRaises(ConnectivityFailure):collector._ensure_connectivity_after_timeout()
