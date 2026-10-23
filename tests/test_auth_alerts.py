# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Behavior tests for authorization, durable sessions and alert delivery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import time
import urllib.error
from unittest.mock import patch, MagicMock

from fixtures import IntegrationFixture, server
from api import auth
from api.store import Sample, SampleStore
from collector.alert_delivery import deliver_due
from collector.collector import Collector


class AccessTests(IntegrationFixture):
    # Inherit only fixture helpers; integration cases explicitly use local mode.
    def setUp(self):
        super().setUp()
        server.settings = replace(self.settings, api_require_login=True,
                                  api_viewer_password_hash=auth.password_hash('viewer-password-example'))
        server._login_buckets.clear()

    def sign_in(self, username='admin', password='integration-test'):
        response = self.client.post('/api/auth/login', json={'username':username,'password':password})
        self.assertEqual(response.status_code, 200)
        return response.json()['csrf_token']

    def test_read_export_docs_require_login_and_health_is_minimal(self):
        for path in ('/api/samples','/api/export','/api/observation','/openapi.json','/docs'):
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertNotIn('rows', self.client.get('/health').json())
        self.assertEqual(self.client.get('/', follow_redirects=False).headers['location'], '/login')

    def test_local_mode_never_serves_the_login_page(self):
        server.settings = replace(self.settings, api_require_login=False)
        response = self.client.get('/login', follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/')
        self.assertFalse(self.client.get('/api/auth/session').json()['login_required'])

    def test_viewer_reads_and_exports_but_cannot_write_even_with_valid_csrf(self):
        csrf = self.sign_in('viewer','viewer-password-example')
        self.assertEqual(self.client.get('/api/export').status_code, 200)
        self.assertEqual(self.client.post('/api/reset',headers={'X-CSRF-Token':csrf}).status_code,403)
        self.assertEqual(self.client.get('/api/auth/session').json()['role'],'viewer')

    def test_admin_cookie_requires_csrf_and_logout_revokes_session(self):
        csrf = self.sign_in()
        self.assertEqual(self.client.post('/api/reset').status_code,403)
        self.assertEqual(self.client.post('/api/reset',headers={'X-CSRF-Token':csrf}).status_code,200)
        old_cookie = self.client.cookies.get(auth.COOKIE)
        self.assertEqual(self.client.post('/api/auth/logout',headers={'X-CSRF-Token':csrf}).status_code,200)
        self.client.cookies.set(auth.COOKIE,old_cookie)
        self.assertEqual(self.client.get('/api/samples').status_code,401)

    def test_session_survives_restart_expires_and_is_stored_as_a_hash(self):
        self.sign_in()
        token=self.client.cookies.get(auth.COOKIE)
        with self.store._connection() as conn:
            row=dict(conn.execute('SELECT * FROM auth_sessions').fetchone())
        self.assertNotIn(token,json.dumps(row))
        reopened=SampleStore(self.path)
        with patch.object(server,'store',reopened):
            self.assertEqual(self.client.get('/api/samples').status_code,200)
            with reopened._connection() as conn:
                conn.execute('UPDATE auth_sessions SET expires_at=?',(time.time()-1,))
            self.assertEqual(self.client.get('/api/samples').status_code,401)
        reopened.close()

    def test_rotation_revokes_cookie_and_scoped_machine_admin_token_still_works(self):
        self.sign_in()
        server.settings=replace(server.settings,api_admin_token='rotated-example-token')
        self.assertEqual(self.client.get('/api/samples').status_code,401)
        self.assertEqual(self.client.get('/api/export',headers={'X-Admin-Token':'rotated-example-token'}).status_code,200)

    def test_bad_logins_are_limited_and_hash_parser_rejects_invalid_input(self):
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'admin','password':'senha inválida'}).status_code,401)
        for _ in range(4):
            self.assertEqual(self.client.post('/api/auth/login',json={'username':'admin','password':'wrong'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'admin','password':'integration-test'}).status_code,429)
        for invalid in ('x', 'other$00$00', 'scrypt$'+'z'*32+'$'+'0'*128):
            self.assertFalse(auth.verify_password('example',invalid))


class AlertTests(IntegrationFixture):
    def create_alert(self):
        return self.store.add_alert('speed_degraded','Example degraded speed',cooldown_seconds=0)

    def test_failed_delivery_retries_after_restart_and_then_succeeds(self):
        alert_id=self.create_alert()
        with patch('collector.alert_delivery.urllib.request.urlopen',side_effect=urllib.error.URLError('secret-url')):
            self.assertEqual(deliver_due(self.store,'https://example.com/private-token',1000),1)
        row=self.store.alerts()[0]
        self.assertEqual(row['delivery_status'],'pending')
        self.assertNotIn('private-token',json.dumps(row))
        self.assertNotIn('secret-url',json.dumps(row))
        self.assertEqual(deliver_due(self.store,'https://example.com',1029),0)
        reopened=SampleStore(self.path)
        response=MagicMock();response.__enter__.return_value.status=204
        with patch('collector.alert_delivery.urllib.request.urlopen',return_value=response) as send:
            self.assertEqual(deliver_due(reopened,'https://example.com',1030),1)
            self.assertEqual(send.call_args.args[0].get_header('Idempotency-key'),f'speedtester-alert-{alert_id}')
        self.assertEqual(reopened.alerts()[0]['delivery_status'],'delivered')
        self.assertEqual(deliver_due(reopened,'https://example.com',2000),0)
        reopened.close()

    def test_concurrent_claims_and_crash_leases_do_not_duplicate_immediate_delivery(self):
        self.create_alert()
        def claim(_):
            store=SampleStore(self.path)
            try:return store.claim_alert_deliveries(1000)
            finally:store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows=list(pool.map(claim,range(2)))
        self.assertEqual(sum(len(row) for row in rows),1)
        self.assertEqual(len(self.store.claim_alert_deliveries(1119)),0)
        self.assertEqual(len(self.store.claim_alert_deliveries(1120)),1)

    def test_six_failed_deliveries_stop_retrying_and_remain_visible(self):
        self.create_alert()
        with patch('collector.alert_delivery.urllib.request.urlopen',side_effect=urllib.error.HTTPError('https://example.com',500,'error',{},None)):
            for now in (1000,2000,4000,8000,16000,32000):
                self.assertEqual(deliver_due(self.store,'https://example.com',now),1)
        self.assertEqual(self.store.alerts()[0]['delivery_status'],'failed')
        self.assertEqual(deliver_due(self.store,'https://example.com',64000),0)

    def test_incident_recovery_is_persisted_once_across_collector_restart(self):
        collector=Collector(self.settings,self.store)
        collector._evaluate_alerts(Sample('2026-10-11T00:00:00Z',is_failure=True,failure_origin='OPERATOR'),None)
        collector._evaluate_alerts(Sample('2026-10-11T01:00:00Z',download_mbps=100,bandwidth_contracted_mbps=1000),None)
        restarted=Collector(self.settings,self.store)
        restarted._evaluate_alerts(Sample('2026-10-11T02:00:00Z',download_mbps=900,bandwidth_contracted_mbps=1000),None)
        restarted._evaluate_alerts(Sample('2026-10-11T03:00:00Z',download_mbps=900,bandwidth_contracted_mbps=1000),None)
        kinds=[row['kind'] for row in self.store.alerts()]
        self.assertEqual(kinds.count('operator_recovered'),1)
        self.assertEqual(kinds.count('speed_recovered'),1)
