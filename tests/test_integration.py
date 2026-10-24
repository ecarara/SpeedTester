# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Deterministic regression tests for API, restart recovery and audit evidence."""
import json
from contextlib import closing
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from api.store import DB_SCHEMA, MeasurementSlot, Sample, SampleStore
from collector.collector import Collector
from collector.connectivity import ConnectivitySnapshot, probe_connectivity

from fixtures import IntegrationFixture, server


class IntegrationTests(IntegrationFixture):
    def test_summary_outliers_keep_row_labels_after_failures_and_missing_metrics(self):
        start = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
        # The failed row and absent upload leave gaps in the metric indices.
        speeds = [900, None, 910, 920, 930, 940, 950, 960, 200]
        self.store.add_samples([
            Sample(
                started_at=(start + timedelta(days=i)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                local_date=(start + timedelta(days=i)).date().isoformat(),
                quadrant='tarde', runner='iperf3', is_failure=speed is None,
                download_mbps=speed, upload_mbps=speed if i != 2 else None,
            )
            for i, speed in enumerate(speeds)
        ])
        for query in ('date=2026-10-16',
                      'from=2026-10-10&to=2026-10-16',
                      'from=2026-09-17&to=2026-10-16',
                      'from=2026-07-19&to=2026-10-16', ''):
            with self.subTest(query=query):
                response = self.client.get('/api/summary?runner=iperf3&' + query)
                self.assertEqual(response.status_code, 200)
        summary = self.client.get('/api/summary?runner=iperf3').json()
        self.assertEqual(summary['failure_count'], 1)
        self.assertEqual(summary['outliers']['download'], [
            {'i': 8, 'value': 200.0, 'zscore': -2.64},
        ])
        self.assertEqual(summary['outliers']['upload'], [
            {'i': 8, 'value': 200.0, 'zscore': -2.44},
        ])

    def test_filters_precede_pagination_and_newest_is_present(self):
        self.add_many()
        all_rows = self.client.get('/api/samples').json()
        self.assertEqual(len(all_rows), 1000)
        self.assertEqual(all_rows[0]['id'], 1007)
        rows = self.client.get('/api/samples?runner=iperf3&date=2026-10-01&limit=2&offset=1').json()
        self.assertEqual([row['id'] for row in rows], [1006, 1005])
        self.assertEqual(self.client.get('/api/summary?runner=iperf3&date=2026-10-01').json()['count'], 7)

    def test_export_includes_every_row_and_respects_filters(self):
        self.add_many()
        response = self.client.get('/api/export?format=json')
        self.assertEqual(len(response.json()), 1007)
        self.assertIn('attachment;', response.headers['content-disposition'])
        csv = self.client.get('/api/export?format=csv&runner=iperf3').text
        self.assertEqual(len(csv.strip().splitlines()), 8)
        self.assertEqual(len(self.client.get('/api/export?format=json&runner=iperf3').json()), 7)

    def test_network_map_aggregates_operator_city_country_without_public_ip(self):
        self.store.add_samples([
            Sample('2026-10-01T12:00:00Z', runner='iperf3', download_mbps=900,
                   upload_mbps=450, isp='Operadora A', isp_organization='Grupo A',
                   country='Brasil', country_code='BR', city='Curitiba',
                   public_ip='203.0.113.10', local_date='2026-10-01', quadrant='tarde'),
            Sample('2026-10-01T13:00:00Z', runner='iperf3', is_failure=True,
                   failure_origin='OPERATOR', isp='Operadora A', country='Brasil',
                   country_code='BR', city='Curitiba', public_ip='203.0.113.10',
                   local_date='2026-10-01', quadrant='tarde'),
        ])
        response = self.client.get('/api/network-map?date=2026-10-01&runner=iperf3')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['totals'], {'samples': 2, 'operators': 1, 'cities': 1, 'countries': 1, 'unmapped': 0})
        point = body['points'][0]
        self.assertEqual(point['operator'], 'Operadora A')
        self.assertEqual(point['city'], 'Curitiba')
        self.assertEqual(point['country'], 'Brasil')
        self.assertEqual(point['coordinate_source'], 'city-centroid')
        self.assertNotIn('public_ip', point)
        self.assertEqual(point['failure_count'], 1)

    def test_invalid_filters_return_422(self):
        for query in ('date=invalid', 'from=2026-10-02&to=2026-10-01', 'runner=unknown',
                      'since=not-a-timestamp', 'minutes=-1', 'date=2026-10-01&from=2026-10-01',
                      'order=random', 'quadrant=invalid'):
            self.assertEqual(self.client.get('/api/samples?' + query).status_code, 422, query)

    def test_local_day_filter_includes_legacy_utc_boundary(self):
        self.store.add_samples([Sample('2026-10-02T02:30:00Z'), Sample('2026-10-02T03:30:00Z')])
        rows = self.client.get('/api/samples?date=2026-10-01').json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['started_at'], '2026-10-02T02:30:00Z')

    def test_admin_routes_require_token(self):
        self.add_many(1)
        self.assertEqual(self.client.post('/api/reset').status_code, 403)
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.client.post('/api/reset', headers={'X-Admin-Token':'wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/api/reset', headers={'X-Admin-Token':'integration-test'}).status_code, 200)
        self.assertEqual(self.store.count(), 0)
        with patch.object(server, 'settings', replace(self.settings, api_admin_token='')):
            self.assertEqual(self.client.post('/api/reset').status_code, 503)

    def test_restart_recovers_recent_slot_and_marks_old_slot_missing(self):
        slot = self.slot()
        self.store.claim_slot(slot['id'])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE measurement_slots SET updated_at='2026-10-11T11:50:00Z'")
        self.store.close()
        self.store = SampleStore(self.path)
        self.assertEqual(self.store.recover_stale_slots('2026-10-11T12:05:00Z'), 1)
        self.assertEqual(self.store.all_slots()[0]['status'], 'PENDING')
        self.assertEqual(len(self.store.due_slots('2026-10-11T12:05:00Z')), 1)
        self.store.claim_slot(slot['id'])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE measurement_slots SET updated_at='2026-10-11T12:05:00Z'")
        self.store.recover_stale_slots('2026-10-11T14:00:00Z')
        self.assertEqual(self.store.all_slots()[0]['status'], 'MISSED_UNKNOWN')
        self.store.close()

    def test_live_lease_is_not_recovered(self):
        slot = self.slot()
        self.store.claim_slot(slot['id'])
        now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.assertEqual(self.store.recover_stale_slots(now), 0)
        self.assertEqual(self.store.all_slots()[0]['status'], 'RUNNING')

    def test_atomic_completion_is_idempotent_under_concurrent_writers(self):
        slot = self.slot(); self.store.claim_slot(slot['id'])
        sample = Sample('2026-10-11T12:00:00Z', slot_id=slot['id'], download_mbps=900)
        def save(_):
            store = SampleStore(self.path)
            try:
                return store.add_sample(sample)
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(save, range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.all_slots()[0]['status'], 'SUCCESS')

    def test_retained_attempts_do_not_change_representative_statistics(self):
        slot = self.slot(); self.store.claim_slot(slot['id'])
        settings = SimpleNamespace(**{**self.settings.__dict__, 'speedtest_runner':'iperf3', 'bandwidth_contracted_mbps':1000})
        first = SimpleNamespace(download_mbps=100, upload_mbps=450, ping_ms=5, jitter_ms=1,
            server_id=None, server_name='example', server_location=None, country=None,
            interface='wlp1', isp=None, bandwidth_contracted_mbps=1000, duration_sec=20,
            connection_type='wifi', connection_source='linux-sysfs', connection_scope='runner_address',
            connection_observed_at='2026-10-11T12:00:00Z',
            connection_evidence={'interface':'wlp1','type':'wifi','scope':'runner_address'})
        second = SimpleNamespace(**{**first.__dict__, 'download_mbps':900,
            'interface':'enp1', 'connection_type':'ethernet',
            'connection_evidence':{'interface':'enp1','type':'ethernet','scope':'runner_address'}})
        collector = Collector(settings, self.store)
        times=[]
        def dispatch():
            times.append(collector._attempt_started_at)
            return first if len(times)==1 else second
        snapshot = ConnectivitySnapshot('192.0.2.1', True, True, {'test':True})
        with patch('collector.collector.probe_connectivity', return_value=snapshot), patch.object(collector, '_dispatch_speedtest', side_effect=dispatch):
            sample = collector._run_single(slot)
        self.assertEqual(sample.started_at, times[1])
        attempts = self.client.get('/api/attempts?slot_id='+str(slot['id'])).json()
        self.assertEqual([row['outcome'] for row in attempts], ['discarded','selected'])
        self.assertEqual([row['metrics']['download_mbps'] for row in attempts], [100,900])
        self.assertEqual([row['metrics']['connection_type'] for row in attempts], ['wifi','ethernet'])
        self.assertEqual([row['metrics']['interface'] for row in attempts], ['wlp1','enp1'])
        saved = self.client.get('/api/samples').json()[0]
        self.assertEqual(saved['connection_type'], 'ethernet')
        self.assertEqual(saved['connection_source'], 'linux-sysfs')
        self.assertEqual(saved['connection_scope'], 'runner_address')
        self.assertEqual(saved['connection_observed_at'], '2026-10-11T12:00:00Z')
        self.assertEqual(json.loads(saved['evidence_json'])['connection'], second.connection_evidence)
        exported = self.client.get('/api/export?format=json').json()[0]
        self.assertEqual(exported['connection_type'], 'ethernet')
        import csv
        import io
        csv_row = next(csv.DictReader(io.StringIO(self.client.get('/api/export?format=csv').text)))
        self.assertEqual(csv_row['connection_type'], 'ethernet')
        self.assertEqual(csv_row['connection_scope'], 'runner_address')
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.client.get('/api/summary').json()['download_avg_mbps'], 900)

    def test_future_slots_do_not_reduce_coverage(self):
        slots=[{'quadrant':'manha','status':'SUCCESS','scheduled_for':'2026-10-11T09:00:00Z'},
               {'quadrant':'tarde','status':'PENDING','scheduled_for':'2026-10-11T15:00:00Z'},
               {'quadrant':'manha','status':'MEASUREMENT_ERROR','scheduled_for':'2026-10-11T10:00:00Z'}]
        result=server._compute_coverage(slots,'2026-10-11T12:00:00Z')
        self.assertEqual(result['expected'], 2)
        self.assertEqual(result['future'], 1)
        self.assertEqual(result['coverage_pct'], 50)
        self.assertEqual(result['classified_pct'], 100)

    def test_gateway_rejecting_probe_ports_does_not_block_working_internet(self):
        with patch('collector.connectivity._default_route', return_value=('192.0.2.1','eth0')), \
             patch('collector.connectivity._probe_host', return_value=[]), \
             patch('collector.connectivity._probe_gateway_icmp', return_value=False), \
             patch('collector.connectivity._probe_dns_and_tcp', return_value={'dns':True,'reachable':True}):
            snapshot = probe_connectivity()
        self.assertTrue(snapshot.gateway_reachable)
        self.assertTrue(snapshot.external_reachable)

    def test_migration_keeps_legacy_data_and_is_repeatable(self):
        path=str(Path(self.tmp.name)/'legacy.db')
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(DB_SCHEMA)
            conn.execute("INSERT INTO schema_meta(key,value) VALUES ('version','11')")
            conn.execute("INSERT INTO samples(started_at,download_mbps,interface) VALUES ('2026-01-01T12:00:00Z',900,'eth0')")
        for _ in range(2):
            store=SampleStore(path)
            self.assertEqual(store.count(),1)
            self.assertIn('runner',store.all_samples()[0])
            self.assertIsNone(store.all_samples()[0]['connection_type'])
            with closing(sqlite3.connect(path)) as conn, conn:
                self.assertEqual(conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0],'12')
            store.close()

    def test_downtime_clips_to_period_and_merges_same_origin(self):
        events=[{'started_at':'2026-10-01T02:00:00Z','ended_at':'2026-10-01T04:00:00Z','event_type':'INTERNAL_OUTAGE'},
                {'started_at':'2026-10-01T03:30:00Z','ended_at':'2026-10-01T04:30:00Z','event_type':'INTERNAL_OUTAGE'}]
        result=server._compute_downtime(server._events_in_period(events,'2026-10-01','2026-10-01'))
        self.assertEqual(result['total_minutes'],90)
        self.assertEqual(result['by_origin_minutes']['INTERNAL_OUTAGE'],90)

    def test_config_does_not_expose_secrets(self):
        result=self.client.get('/api/config').json()
        self.assertEqual(result['timezone'],'America/Sao_Paulo')
        self.assertNotIn('integration-test',json.dumps(result))
        self.assertNotIn('api_admin_token', result)

    def test_chart_series_covers_entire_period_and_large_series_are_aggregated(self):
        self.add_many(1007)
        series = self.client.get('/api/series?date=2026-10-01').json()
        self.assertEqual(series['count'], 1007)
        self.assertEqual(len(series['rows']), 1007)
        self.assertFalse(series['aggregated'])
        self.add_many(1007)
        series = self.client.get('/api/series?date=2026-10-01').json()
        self.assertEqual(series['count'], 2014)
        self.assertEqual(len(series['rows']), 1)
        self.assertTrue(series['aggregated'])
        self.assertEqual(series['rows'][0]['download_mbps'], 900)

    def test_availability_timeline_obeys_period_in_operational_timezone(self):
        self.store.add_availability_event('2026-10-01T02:30:00Z', '2026-10-01T03:30:00Z',
                                          'INTERNAL_OUTAGE', 'test', 'high', 'test')
        rows = self.client.get('/api/availability-events?date=2026-10-01').json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(datetime.fromisoformat(rows[0]['started_at']), datetime(2026,10,1,3,tzinfo=timezone.utc))
        self.assertEqual(self.client.get('/api/availability-events?from=2026-10-02&to=2026-10-03').json(), [])


if __name__ == '__main__':
    unittest.main()
