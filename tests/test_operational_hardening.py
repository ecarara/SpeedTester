# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Bounded input, recovery evidence, immutable scans and notification failures."""
import asyncio
from collections import deque
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fixtures import IntegrationFixture, server
from api.request_limits import RequestSizeLimit, allow_request

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import check_restore
import export_backup
import maintenance
import operations
import recheck_images
import retention
import sync_onedrive
import update_native_tools
from test_deploy_observation import deployment


class RequestLimitTests(IntegrationFixture):
    def test_oversized_login_never_authenticates_or_creates_a_session(self):
        with patch.object(server, 'settings', replace(self.settings, api_max_body_bytes=1024)), \
             patch.object(server.auth, 'authenticate') as authenticate:
            response = self.client.post('/api/auth/login', json={'username': 'admin', 'password': 'x' * 2000})
        self.assertEqual(response.status_code, 413)
        authenticate.assert_not_called()
        with self.store._connection() as database:
            self.assertEqual(database.execute('SELECT COUNT(*) FROM auth_sessions').fetchone()[0], 0)

    def test_real_chunk_bytes_reject_absent_or_understated_length_before_downstream(self):
        async def exercise(headers, messages):
            downstream = Mock()
            async def application(*args):
                downstream()
            sent = []
            async def receive():
                return messages.pop(0)
            async def send(message):
                sent.append(message)
            await RequestSizeLimit(application, lambda: 4)({'type': 'http', 'headers': headers}, receive, send)
            downstream.assert_not_called()
            return sent[0]['status']
        for headers in ([], [(b'content-length', b'1')]):
            messages = [{'type': 'http.request', 'body': b'ab', 'more_body': True},
                        {'type': 'http.request', 'body': b'cde', 'more_body': False}]
            self.assertEqual(asyncio.run(exercise(headers, messages)), 413)
        for value in (b'bad', b'9' * 100):
            self.assertEqual(asyncio.run(exercise([(b'content-length', value)], [])), 400)

    def test_exact_limit_disconnect_and_non_http(self):
        async def exercise(scope, messages):
            captured = []
            async def application(scope, receive, send):
                if scope['type'] == 'http':
                    captured.append((await receive())['body'])
                    captured.append((await receive())['type'])
                else:
                    captured.append('non-http')
            async def receive():
                return messages.pop(0)
            await RequestSizeLimit(application, lambda: 4)(scope, receive, Mock())
            return captured
        scope = {'type': 'http', 'headers': []}
        self.assertEqual(asyncio.run(exercise(scope, [{'type': 'http.request', 'body': b'abcd'},
                                                     {'type': 'http.disconnect'}])), [b'abcd', 'http.disconnect'])
        self.assertEqual(asyncio.run(exercise(scope, [{'type': 'http.disconnect'}])), [])
        self.assertEqual(asyncio.run(exercise({'type': 'websocket'}, [])), ['non-http'])

    def test_new_live_clients_cannot_expand_either_limiter(self):
        for buckets in ({'one': deque([1.0])}, {'one': deque()}):
            allowed = allow_request(buckets, 'two', 2.0, 2, 1)
            self.assertEqual(allowed, not bool(buckets.get('one')))
            self.assertLessEqual(len(buckets), 1)
        buckets = {}
        self.assertTrue(allow_request(buckets, 'one', 1, 1, 1))
        self.assertFalse(allow_request(buckets, 'one', 2, 1, 1))
        self.assertTrue(allow_request(buckets, 'two', 62, 1, 1))
        self.assertTrue(allow_request(buckets, 'two', 123, 1, 1))
        for value in (0, 10001):
            with self.assertRaises(ValueError): replace(self.settings, api_rate_limit_max_clients=value)
        for value in (10, 1048577):
            with self.assertRaises(ValueError): replace(self.settings, api_max_body_bytes=value)


class TempTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def database(self, name='source.db'):
        path = self.root / name
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE samples (download_mbps REAL)')
            db.execute('INSERT INTO samples VALUES (900)')
        return path


class RecoveryTests(TempTests):
    def test_complete_restore_compares_all_tables_and_leaves_source_unchanged(self):
        source = self.database()
        original = source.read_bytes()
        result = check_restore.check(source)
        self.assertEqual(result['rows'], 1)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [source])
        with patch.object(check_restore, 'signature', side_effect=[({}, 'one'), ({}, 'two')]):
            with self.assertRaises(ValueError): check_restore.check(source)
        with patch.object(sys, 'argv', ['check', str(source)]): check_restore.main()

    def test_foreign_or_corrupt_database_is_rejected(self):
        with sqlite3.connect(self.root / 'foreign.db') as db:
            db.execute('CREATE TABLE foreign_table (value TEXT)')
        with self.assertRaises(ValueError): check_restore.signature(self.root / 'foreign.db')
        with patch.object(check_restore.sqlite3, 'connect') as connect:
            connect.return_value.execute.return_value.fetchone.return_value = ('bad',)
            with self.assertRaises(ValueError): check_restore.signature(self.root / 'foreign.db')

    def test_export_only_success_marker_is_immutable_and_private(self):
        source = self.root / 'backups'; source.mkdir()
        name = 'speedtester-20261011T010203Z-123.db'
        (source / name).write_bytes(b'snapshot')
        (source / '.last-success.json').write_text(json.dumps({'filename': name}))
        outbox = self.root / 'exports'
        self.assertEqual(export_backup.export(source, outbox), name)
        self.assertEqual(export_backup.export(source, outbox), name)
        self.assertEqual((outbox / name).stat().st_mode & 0o777, 0o600)
        (outbox / name).write_bytes(b'changed')
        with self.assertRaises(ValueError): export_backup.export(source, outbox)
        (source / '.last-success.json').write_text(json.dumps({'filename': '../outside.db'}))
        with self.assertRaises(ValueError): export_backup.export(source, outbox)
        (source / '.last-success.json').write_text(json.dumps({'filename': name}))
        (outbox / name).unlink()
        with patch.object(export_backup, 'file_hash', side_effect=['one', 'two']):
            with self.assertRaises(ValueError): export_backup.export(source, outbox)
        self.assertEqual(list(outbox.iterdir()), [])
        with patch.object(sys, 'argv', ['export', '--source', str(source), '--destination', str(outbox)]): export_backup.main()

    def test_one_drive_requires_crypt_and_verifies_copy_without_deleting_remote(self):
        folder = self.root / 'outbox'; folder.mkdir()
        config = self.root / 'rclone.conf'; config.write_text('private'); config.chmod(0o600)
        status = folder / '.sync-status.json'
        results = [SimpleNamespace(stdout=json.dumps({'secure': {'type': 'crypt'}})),
                   SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)]
        with patch.object(sync_onedrive.subprocess, 'run', side_effect=results) as execute:
            evidence = sync_onedrive.sync(folder, config, 'secure:SpeedTester', status)
        self.assertEqual(evidence['status'], 'passed')
        commands = [call.args[0] for call in execute.call_args_list]
        self.assertIn('copy', commands[1]); self.assertIn('--immutable', commands[1])
        self.assertIn('cryptcheck', commands[2]); self.assertNotIn('sync', commands[1])
        config.chmod(0o644)
        with self.assertRaises(ValueError): sync_onedrive.sync(folder, config, 'secure:', status)
        config.chmod(0o600)
        with self.assertRaises(ValueError): sync_onedrive.sync(folder, config, '--bad', status)
        with patch.object(sync_onedrive.subprocess, 'run', return_value=SimpleNamespace(stdout='{"secure":{"type":"onedrive"}}')):
            with self.assertRaises(ValueError): sync_onedrive.sync(folder, config, 'secure:', status)
        with patch.object(sync_onedrive.subprocess, 'run', side_effect=[results[0], SimpleNamespace(returncode=1)]):
            with self.assertRaises(RuntimeError): sync_onedrive.sync(folder, config, 'secure:', status)
        self.assertEqual(json.loads(status.read_text())['status'], 'failed')
        with self.assertRaises(ValueError): sync_onedrive.sync(self.root / 'missing', config, 'secure:', status)
        with patch.object(sys, 'argv', ['sync', '--folder', str(folder), '--config', str(config), '--remote', 'secure:', '--status', str(status)]), patch.object(sync_onedrive, 'sync', return_value={}): sync_onedrive.main()


class RecheckTests(TempTests):
    def images(self):
        return {service: 'ghcr.io/ecarara/speedtester-' + service + '@sha256:' + 'a' * 64
                for service in ('api', 'collector', 'backup')}

    def execute(self, args, **kwargs):
        vulnerability = {'id': 'test-CVE', 'severity': 'Critical', 'fix': {'state': 'wont-fix'}}
        kwargs['stdout'].write(json.dumps({'descriptor': {'db': {'status': {'valid': True}}},
                                         'matches': [{'vulnerability': vulnerability}]}))
        return SimpleNamespace(returncode=0)

    def test_both_architectures_use_digests_and_new_database_with_raw_findings(self):
        output = self.root / 'reports'
        with patch.object(recheck_images.subprocess, 'run', side_effect=self.execute) as execute:
            result = recheck_images.scan(self.images(), output)
        self.assertEqual(execute.call_count, 6)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue((output / 'api-amd64.json').exists())
        self.assertEqual(execute.call_args.kwargs['env']['GRYPE_DB_MAX_ALLOWED_BUILT_AGE'], '24h')
        self.assertIn('@sha256:', execute.call_args.args[0][1])
        state = self.root / 'deployment.json'; state.write_text(json.dumps({'images': self.images()}))
        with patch.object(sys, 'argv', ['scan', '--state', str(state), '--output', str(self.root / 'other'), '--status-file', str(self.root / 'status.json')]), patch.object(recheck_images, 'scan', return_value=result):
            with self.assertRaises(SystemExit): recheck_images.main()
        self.assertEqual(json.loads((self.root / 'status.json').read_text())['status'], 'failed')
        with patch.object(sys, 'argv', ['scan', '--state', str(state), '--output', str(self.root / 'other')]), patch.object(recheck_images, 'scan', return_value={**result, 'status': 'passed'}): recheck_images.main()

    def test_untrusted_refs_invalid_platform_partial_images_or_scan_failures_reject(self):
        for images, platforms in (({'api': 'image:main'}, ('linux/amd64',)),
                                  ({'wrong': self.images()['api']}, ('linux/amd64',)),
                                  (self.images(), ('bad',))):
            with self.assertRaises(ValueError): recheck_images.scan(images, self.root / str(len(list(self.root.iterdir()))), platforms=platforms)
        with patch.object(recheck_images.subprocess, 'run', return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(RuntimeError): recheck_images.scan(self.images(), self.root / 'failed')
        with patch.object(recheck_images.subprocess, 'run', side_effect=self.execute):
            with self.assertRaises(ValueError): recheck_images.scan({'api': self.images()['api']}, self.root / 'partial')
        with patch.object(recheck_images.subprocess, 'run', side_effect=self.execute), patch.object(recheck_images, 'check_report', return_value={'blocking_findings': 0}):
            self.assertEqual(recheck_images.scan(self.images(), self.root / 'passed')['status'], 'passed')

    def test_new_findings_block_before_any_service_stop(self):
        with patch.object(deployment, 'release_source', return_value=self.root), \
             patch.object(deployment, 'image_digests', return_value=self.images()), \
             patch.object(deployment, 'fresh_image_gate', side_effect=RuntimeError('new CVE')), \
             patch.object(deployment, 'run') as execute:
            with self.assertRaises(RuntimeError): deployment.deploy(self.root, 'a' * 40, 'fixture', 'db', 'backup')
        execute.assert_not_called()
        with patch.dict(os.environ, {'SECURITY_REPORT_ROOT': str(self.root / 'reports')}), patch.object(deployment, 'run') as execute:
            path = deployment.fresh_image_gate(self.root, self.root, self.images(), 'a' * 40)
        self.assertIn('recheck-', path)
        self.assertIn('--state', execute.call_args.args)
        state_path = execute.call_args.args[execute.call_args.args.index('--state') + 1]
        self.assertFalse(Path(state_path).exists())
        deployment.deployment_status(self.root, 'waiting')
        before = json.loads((self.root / '.deploy-status.json').read_text())['since']
        deployment.deployment_status(self.root, 'waiting')
        self.assertEqual(json.loads((self.root / '.deploy-status.json').read_text())['since'], before)
        deployment.deployment_status(self.root, 'failed')


class RetentionTests(TempTests):
    def test_current_and_rollback_release_snapshot_and_evidence_are_preserved(self):
        reports = self.root / 'reports'; outbox = self.root / 'outbox'
        for folder in ('releases', 'deployment-backups', 'reports', 'outbox'):
            (self.root / folder).mkdir()
        for index in ('a', 'b', 'c'):
            sha = index * 40
            (self.root / 'releases' / sha).mkdir()
            name = '20261011T010203000000-' + sha + '.db'
            (self.root / 'deployment-backups' / name).write_text('snapshot')
            report = '20261011T010203000000-' + sha
            (reports / report).mkdir()
            for path in (self.root / 'releases' / sha, self.root / 'deployment-backups' / name, reports / report):
                os.utime(path, (0, 0))
            if index != 'c':
                state = {'revision': sha, 'backup': name, 'security': {'baseline_report': str(reports / report)}}
                (self.root / ('deployment.json' if index == 'a' else 'previous-deployment.json')).write_text(json.dumps(state))
        unrelated = self.root / 'releases' / 'keep.txt'; unrelated.write_text('keep'); os.utime(unrelated, (0, 0))
        link = self.root / 'releases' / ('d' * 40); link.symlink_to(reports, target_is_directory=True)
        name = 'speedtester-20261011T010203Z-123.db'
        (outbox / name).write_text('pending'); os.utime(outbox / name, (0, 0))
        result = retention.cleanup(self.root, reports, outbox, now=40 * 86400)
        self.assertEqual(result, {'releases': 1, 'deployment-backups': 1, 'reports': 1, 'outbox': 0})
        self.assertTrue(link.is_symlink()); self.assertTrue(unrelated.exists())
        (outbox / '.sync-status.json').write_text(json.dumps({'status': 'passed', 'checked_at': 86400}))
        self.assertEqual(retention.cleanup(self.root, reports, outbox, now=40 * 86400)['outbox'], 1)
        with self.assertRaises(ValueError): retention.prune(outbox, retention.PATTERNS['outbox'], 1)
        self.assertEqual(retention.prune(self.root / 'absent', retention.PATTERNS['outbox'], 30), [])
        with patch.object(sys, 'argv', ['retain', '--root', str(self.root), '--reports', str(reports), '--outbox', str(outbox)]): retention.main()


class MonitorTests(TempTests):
    def test_confirmation_deduplication_recovery_and_cooldown(self):
        state = {}; facts = {'disk_low': True}
        for now in (100, 400, 700): state, events = operations.incidents(state, facts, now)
        self.assertEqual(len(events), 1)
        state, events = operations.incidents(state, facts, 1000)
        self.assertEqual(events, [])
        state, events = operations.incidents(state, facts, 22300)
        self.assertEqual(len(events), 1)
        state, events = operations.incidents(state, {'disk_low': False}, 22600)
        self.assertEqual(events[0]['kind'], 'ops_recovered')
        _, events = operations.incidents(state, {'disk_low': False}, 22900)
        self.assertEqual(events, [])

    def test_email_still_sends_when_dashboard_is_unavailable_and_retry_is_persisted(self):
        event = {'kind': 'ops_disk_low', 'message': 'Example', 'severity': 'critical', 'created_at': 100}
        with patch.object(operations, 'dashboard_delivery', side_effect=RuntimeError('offline')), \
             patch.object(operations, 'email_delivery') as email:
            pending = operations.deliver('fixture', [event], 100)
            email.assert_called_once()
        self.assertTrue(pending[0]['email_delivered'])
        with patch.object(operations, 'dashboard_delivery') as dashboard, patch.object(operations, 'email_delivery') as email:
            self.assertEqual(operations.deliver('fixture', pending, 101), pending)
            dashboard.assert_not_called()
            self.assertEqual(operations.deliver('fixture', pending, 1000), [])
            email.assert_not_called()
        with patch.object(operations, 'collect', return_value={'disk_low': True}), patch.object(operations, 'deliver', side_effect=lambda p,q,n:q):
            for now in (100, 400, 700): operations.monitor(self.root, 'fixture', 'backup', self.root / 'state', now)
        state = json.loads((self.root / 'state/monitor.json').read_text())
        self.assertEqual(len(state['pending']), 1)
        self.assertEqual((self.root / 'state/monitor.json').stat().st_mode & 0o777, 0o600)

    def test_smtp_uses_validated_tls_secret_file_and_generic_content(self):
        event = {'message': 'Example incident', 'severity': 'critical', 'created_at': 100}
        secret = self.root / 'smtp-password'; secret.write_text('test-password'); secret.chmod(0o600)
        environment = {'ALERT_EMAIL_TO':'owner@example.com','ALERT_EMAIL_FROM':'alerts@example.com',
                       'SMTP_HOST':'smtp.example.com','SMTP_USER':'user','SMTP_PASSWORD_FILE':str(secret)}
        smtp = Mock(); smtp.__enter__ = Mock(return_value=smtp); smtp.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, environment, clear=True), patch.object(operations.smtplib, 'SMTP', return_value=smtp):
            operations.email_delivery(event)
            smtp.starttls.assert_called_once(); smtp.login.assert_called_once_with('user', 'test-password')
            self.assertNotIn('password', smtp.send_message.call_args.args[0].as_string())
        smtp.reset_mock()
        with patch.dict(os.environ, {**environment,'SMTP_PORT':'465'}, clear=True), patch.object(operations.smtplib, 'SMTP_SSL', return_value=smtp):
            operations.email_delivery({**event, 'severity': 'info'}); smtp.starttls.assert_not_called()
        with patch.dict(os.environ, {}, clear=True): operations.email_delivery(event)

    def test_collection_checks_staleness_disk_and_security_and_failed_commands_are_private(self):
        (self.root / 'deployment.json').write_text('{}')
        state = self.root / 'state'; state.mkdir()
        operations.private_json(state / 'images.json', {'status':'passed','checked_at':1000})
        operations.private_json(state / 'restore.json', {'status':'passed','checked_at':1000})
        operations.private_json(self.root / '.deploy-status.json', {'status':'waiting','since':1})
        containers = {'api':{'running':True,'restarts':0,'id':'one'}}
        with patch.object(operations,'api_facts',return_value={'collector_ok':True,'latest_sample':'1970-01-01T00:16:40Z'}), patch.object(operations,'container_facts',return_value=containers), patch.object(operations,'backup_facts',return_value={'completed_at':1000}), patch.object(operations.shutil,'disk_usage',return_value=SimpleNamespace(free=20*1024**3,total=100*1024**3)):
            facts = operations.collect(self.root,'fixture','backup',state,1000)
        self.assertFalse(any(facts.values()))
        with patch.object(operations,'api_facts',side_effect=RuntimeError('secret')),patch.object(operations,'container_facts',side_effect=RuntimeError('secret')),patch.object(operations.shutil,'disk_usage',return_value=SimpleNamespace(free=1,total=100)):
            self.assertTrue(operations.collect(self.root,'fixture','backup',state,9000)['deploy_blocked'])
        operations.private_json(self.root/'.sync-status.json',{'status':'failed'})
        with patch.dict(os.environ,{'ONEDRIVE_REMOTE':'secure:','BACKUP_OUTBOX':str(self.root)}): self.assertTrue(operations.report_facts(self.root,state,1000)['sync_failed'])
        self.assertEqual(operations.age(None,100),float('inf'))
        with patch.object(operations.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='secret')):
            with self.assertRaisesRegex(RuntimeError,'withheld'): operations.execute(['fake'])
        with patch.object(operations.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=' ok ')):
            self.assertEqual(operations.execute(['fake']),'ok')

    def test_https_monitor_requires_trusted_ca_and_rejects_tls_failure(self):
        response = Mock(); response.status = 200
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        with patch.dict(os.environ, {'HTTPS_HEALTH_URL':'https://example.com/health'}), patch.object(operations.urllib.request,'urlopen',return_value=response):
            self.assertTrue(operations.https_health())
        with patch.dict(os.environ, {'HTTPS_HEALTH_URL':'https://example.com/health'}), patch.object(operations.urllib.request,'urlopen',side_effect=OSError('TLS failure')):
            self.assertFalse(operations.https_health())

    def test_restart_window_and_sanitized_facts(self):
        state = self.root / 'state'
        containers = {'api':{'id':'one','running':True,'restarts':3}}
        self.assertTrue(operations.restart_problem(containers,state,100))
        self.assertTrue(operations.restart_problem({'api':{'id':'one','running':True,'restarts':3}},state,400))
        self.assertFalse(operations.restart_problem({'api':{'id':'one','running':True,'restarts':3}},state,4000))
        data = [{'Name':'api','Id':'one','State':{'Running':True},'RestartCount':0,'Config':{'Env':['SECRET=hidden']}}]
        with patch.object(operations,'execute',return_value=json.dumps(data)):
            self.assertNotIn('hidden',json.dumps(operations.container_facts('fixture')))
        with patch.object(operations,'execute',return_value='{"collector_ok":true}'):
            self.assertTrue(operations.api_facts('fixture')['collector_ok'])
        with patch.object(operations,'execute') as execute:
            operations.dashboard_delivery('fixture',{'kind':'example'})
            self.assertEqual(json.loads(execute.call_args.args[1]),{'kind':'example'})

    def test_recovery_runs_networkless_without_mounting_live_database_and_records_failure(self):
        (self.root/'deployment.json').write_text(json.dumps({'images':{'backup':'verified-image'}}))
        name='speedtester-20261011T010203Z-1.db'
        with patch.object(operations,'execute',side_effect=[name,'restore-ok\n{"status":"passed","rows":1}']) as execute:
            result=operations.recovery(self.root,'backups',self.root/'state',self.root/'outbox')
        self.assertEqual(result['status'],'passed')
        command=execute.call_args.args[0]
        self.assertIn('none',command); self.assertIn('backups:/backups:ro',command)
        self.assertNotIn('/data',str(command)); self.assertIn('--read-only',command)
        with patch.object(operations,'execute',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError): operations.recovery(self.root,'backups',self.root/'state',self.root/'outbox')
        self.assertEqual(operations.load_json(self.root/'state/restore.json')['status'],'failed')
        with patch.object(operations,'execute',return_value='{}'): self.assertEqual(operations.backup_facts({'images':{'backup':'image'}},'backup'),{})


class MaintenanceTests(TempTests):
    def test_weekly_evidence_is_fail_closed_and_backup_exports_before_cleanup(self):
        (self.root/'deployment.json').write_text(json.dumps({'revision':'a'*40,'images':{}}))
        with patch.object(maintenance,'scan',return_value={'status':'passed','checked_at':100}) as scan:
            self.assertEqual(maintenance.recheck(self.root,self.root/'reports',self.root/'state')['status'],'passed')
            self.assertIn('a'*40,str(scan.call_args.args[1]))
        with patch.object(maintenance,'scan',side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError): maintenance.recheck(self.root,self.root/'reports',self.root/'state')
        self.assertEqual(operations.load_json(self.root/'state/images.json')['status'],'failed')
        with patch.object(maintenance,'recovery',return_value={'status':'passed'}),patch.object(maintenance,'cleanup') as cleanup,patch.object(maintenance,'sync') as sync,patch.dict(os.environ,{'ONEDRIVE_REMOTE':'secure:','RCLONE_CONFIG':str(self.root/'config')}):
            maintenance.backup(self.root,'backups',self.root/'state',self.root/'outbox',self.root/'reports')
        sync.assert_called_once();cleanup.assert_called_once()
        for mode in ('backup','recheck'):
            argv=['maintain',mode,'--root',str(self.root),'--backup-volume','backups','--state-dir',str(self.root/'state'),'--reports',str(self.root/'reports'),'--outbox',str(self.root/'outbox')]
            with patch.object(sys,'argv',argv),patch.object(maintenance,mode,return_value={'status':'passed'}):maintenance.main()
            with patch.object(sys,'argv',argv),patch.object(maintenance,mode,return_value={'status':'failed'}):
                with self.assertRaises(SystemExit):maintenance.main()
        for mode in ('monitor','recovery'):
            argv=['ops',mode,'--root',str(self.root),'--project','fixture','--backup-volume','backups','--state-dir',str(self.root/'state'),'--outbox',str(self.root/'outbox')]
            with patch.object(sys,'argv',argv),patch.object(operations,mode,return_value={'status':'passed'}):operations.main()
        with patch.object(sys,'argv',['ops','recovery','--root',str(self.root),'--backup-volume','backups','--state-dir',str(self.root/'state')]):
            with self.assertRaises(SystemExit):operations.main()


class NativeUpdateTests(TempTests):
    def fixture(self):
        for name in ('docker/backup','docker/collector','docs'): (self.root/name).mkdir(parents=True)
        (self.root/'docker/backup/Dockerfile').write_text('ADD --checksum=sha256:'+'a'*64+' https://example/openssh-10.6p1.tar.gz\nfilippo.io/age/cmd/age@v1.3.2\nfilippo.io/age@v1.3.2/LICENSE')
        (self.root/'docker/collector/Dockerfile').write_text('ADD --checksum=sha256:'+'b'*64+' https://example/iperf-3.22.tar.gz')
        (self.root/'docs/third-party.md').write_text('OpenSSH 10.6p1 iPerf3 3.22 age 1.3.2')

    def test_stable_versions_update_all_paths_checksums_and_license_reference(self):
        self.fixture()
        releases=[[{'name':'V_10_7_P1'},{'name':'untrusted'}],{'tag_name':'3.23'},{'tag_name':'v1.3.3'}]
        with patch.object(update_native_tools,'upstream_json',side_effect=releases),patch.object(update_native_tools,'download',return_value=b'official-source'):
            changes=update_native_tools.prepare(self.root)
        self.assertEqual(len(changes),3)
        backup=(self.root/'docker/backup/Dockerfile').read_text()
        self.assertIn('10.7p1',backup);self.assertIn('@v1.3.3/LICENSE',backup)
        self.assertNotIn('a'*64,backup)
        with patch.object(update_native_tools,'download',return_value=b'{}'):self.assertEqual(update_native_tools.upstream_json('fixture'),{})
        with patch.object(update_native_tools.urllib.request,'urlopen',return_value=io.BytesIO(b'12345')):
            with self.assertRaises(ValueError):update_native_tools.download('https://example.invalid',limit=4)
        with patch.object(update_native_tools.urllib.request,'urlopen',return_value=io.BytesIO(b'123')):self.assertEqual(update_native_tools.download('https://example.invalid',limit=4),b'123')
        self.assertEqual(update_native_tools.replace_archive('unchanged','3.22','3.22','unused'),'unchanged')
        with patch.object(update_native_tools,'download',return_value=b'payload'):
            with self.assertRaises(ValueError):update_native_tools.replace_archive('missing','3.22','3.23','unused')
        with patch.object(update_native_tools,'prepare',return_value=changes):update_native_tools.main()

    def test_unexpected_tags_prereleases_and_injected_versions_never_mutate_files(self):
        self.fixture()
        cases=[([],),([{'name':'V_10_6_P1'}],{'tag_name':'3.23','prerelease':True}),
               ([{'name':'V_10_6_P1'}],{'tag_name':'3.22'},{'tag_name':'v1.3.3;bad'})]
        for responses in cases:
            before=(self.root/'docker/backup/Dockerfile').read_text()
            with patch.object(update_native_tools,'upstream_json',side_effect=responses):
                with self.assertRaises(ValueError):update_native_tools.prepare(self.root)
            self.assertEqual((self.root/'docker/backup/Dockerfile').read_text(),before)
