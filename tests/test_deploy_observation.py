# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Deployment rollback and observation evidence use disposable state."""
from datetime import datetime, timedelta, timezone
from importlib.util import spec_from_file_location, module_from_spec
import json
from pathlib import Path
import io
import sqlite3
import subprocess
import tarfile
from unittest.mock import patch

from fixtures import IntegrationFixture
from api.store import MeasurementSlot, Sample
from shared.observation import start_observation, report

spec=spec_from_file_location('deployment',Path(__file__).resolve().parents[1]/'scripts/deploy.py')
deployment=module_from_spec(spec);spec.loader.exec_module(deployment)


class DeployTests(IntegrationFixture):
    def test_source_archive_is_extracted_once_and_traversal_is_refused(self):
        root=Path(self.tmp.name)
        def archive(name):
            data=io.BytesIO()
            with tarfile.open(fileobj=data,mode='w:gz') as stream:
                item=tarfile.TarInfo(name);item.size=1;stream.addfile(item,io.BytesIO(b'x'))
            data.seek(0);return data
        with patch.object(deployment.urllib.request,'urlopen',return_value=archive('project/docker/compose.yaml')):
            release=deployment.release_source(root,'a'*40)
            self.assertTrue((release/'docker/compose.yaml').exists())
        with patch.object(deployment.urllib.request,'urlopen',side_effect=AssertionError('unexpected download')):
            self.assertEqual(deployment.release_source(root,'a'*40),release)
        with patch.object(deployment.urllib.request,'urlopen',return_value=archive('../../escaped')):
            with self.assertRaises(tarfile.TarError):deployment.release_source(root,'b'*40)
        self.assertFalse((root/'escaped').exists())

    def test_command_failure_does_not_expose_captured_configuration(self):
        self.assertEqual(deployment.run('python3','-c','print("ok")'),'ok')
        with self.assertRaises(RuntimeError) as error:
            deployment.run('python3','-c','import sys;print("secret-example");sys.exit(1)')
        self.assertNotIn('secret-example',str(error.exception))

    def test_pre_migration_backup_contains_a_valid_copy(self):
        root=Path(self.tmp.name)
        self.store.add_sample(Sample('2026-10-11T00:00:00Z',download_mbps=900))
        def execute(*args):
            code=args[-1].replace('file:/data/speedtester.db','file:'+self.path).replace('/snapshots/',str(root/'deployment-backups')+'/')
            exec(code,{'__builtins__':__builtins__})
            return ''
        with patch.object(deployment,'run',side_effect=execute):
            name=deployment.backup_database(root,'example-image','example-volume','a'*40)
        with sqlite3.connect(root/'deployment-backups'/name) as database:
            self.assertEqual(database.execute('SELECT download_mbps FROM samples').fetchone()[0],900)
            self.assertEqual(database.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        with patch.object(deployment,'run') as command:
            deployment.restore_database(root,'example-image','example-volume',name)
            self.assertIn('--services-stopped',command.call_args.args[-1])

    def test_pulled_image_digests_are_pinned_for_each_service(self):
        sha='a'*40
        def execute(*args):
            if 'pull' in args:return ''
            service=args[-1].split('speedtester-')[1].split(':')[0]
            image={'Config':{'Labels':{'org.opencontainers.image.revision':sha}},'RepoDigests':[f'ghcr.io/ecarara/speedtester-{service}@sha256:'+'b'*64]}
            return json.dumps([image])
        with patch.object(deployment,'run',side_effect=execute), patch.object(deployment,'verify_attestation') as verify:
            images=deployment.image_digests(sha)
            self.assertEqual(len(images),3)
            self.assertTrue(all('@sha256:' in image for image in images.values()))
            self.assertEqual(verify.call_count,3)

    def test_checks_must_all_pass_on_current_revision_and_latest_run(self):
        sha='a'*40
        runs=[{'id':i,'head_sha':sha,'name':name,'path':path,'event':'push','head_branch':'main',
               'status':'completed','conclusion':'success'} for i,(name,path) in enumerate(deployment.WORKFLOWS.items())]
        with patch.object(deployment,'fetch_json',side_effect=[{'commit':{'sha':sha}},{'workflow_runs':runs}]):
            self.assertEqual(deployment.eligible_revision(),sha)
        runs.append({**runs[0],'id':100,'conclusion':'failure'})
        with patch.object(deployment,'fetch_json',side_effect=[{'commit':{'sha':sha}},{'workflow_runs':runs}]):
            self.assertIsNone(deployment.eligible_revision())

    def candidate(self):
        root=Path(self.tmp.name); release=root/'releases'/'candidate';release.mkdir(parents=True)
        images={service:'sha256:'+'a'*64 for service in deployment.SERVICES}
        deployment.save_json(root/'deployment.json',{'revision':'b'*40,'release_dir':str(root),'images':images})
        return root,release,images

    def test_healthy_deploy_takes_backup_before_start_and_records_digest(self):
        root,release,images=self.candidate(); calls=[]
        with patch.object(deployment,'release_source',return_value=release),patch.object(deployment,'image_digests',return_value=images),patch.object(deployment,'run',side_effect=lambda *args:calls.append(args) or ''),patch.object(deployment,'backup_database',side_effect=lambda *args:calls.append(('snapshot',)) or 'snapshot.db'),patch.object(deployment,'validate_service'),patch.object(deployment,'validate_policy'),patch.object(deployment,'staging_baseline',return_value='private-report'):
            self.assertEqual(deployment.deploy(root,'a'*40,'example','db','backups'),'deployed')
        snapshot_index=calls.index(('snapshot',))
        start_index=next(i for i,call in enumerate(calls) if 'up' in call)
        self.assertLess(snapshot_index,start_index)
        state=json.loads((root/'deployment.json').read_text())
        self.assertEqual(state['images'],images)
        self.assertEqual(state['revision'],'a'*40)
        self.assertEqual(state['security']['zap_mode'],'baseline')
        self.assertEqual((root/'deployment.json').stat().st_mode & 0o777,0o600)
        self.assertEqual(deployment.deploy(root,'a'*40,'example','db','backups'),'unchanged')

    def test_unhealthy_release_restores_snapshot_and_restarts_previous_images(self):
        root,release,images=self.candidate();calls=[]
        with patch.object(deployment,'release_source',return_value=release),patch.object(deployment,'image_digests',return_value=images),patch.object(deployment,'run',side_effect=lambda *args:calls.append(args) or ''),patch.object(deployment,'backup_database',return_value='snapshot.db'),patch.object(deployment,'restore_database') as restore,patch.object(deployment,'validate_service',side_effect=RuntimeError('not healthy')),patch.object(deployment,'validate_policy'):
            with self.assertRaises(RuntimeError):deployment.deploy(root,'a'*40,'example','db','backups')
        restore.assert_called_once()
        self.assertIn(str(root/'deploy-previous.json'),calls[-1])
        self.assertIn('up',calls[-1])
        self.assertEqual(json.loads((root/'deployment.json').read_text())['revision'],'b'*40)
        with self.assertRaises(ValueError):deployment.deploy(root,'main;invalid','example','db','backups')

    def test_policy_failure_does_not_stop_running_services(self):
        root,release,images=self.candidate()
        with patch.object(deployment,'release_source',return_value=release), \
             patch.object(deployment,'image_digests',return_value=images), \
             patch.object(deployment,'run') as execute, \
             patch.object(deployment,'validate_policy',side_effect=RuntimeError('policy rejected')):
            with self.assertRaisesRegex(RuntimeError,'policy rejected'):
                deployment.deploy(root,'a'*40,'example','db','backups')
        self.assertFalse(any('stop' in call.args or 'up' in call.args for call in execute.call_args_list))

    def test_baseline_failure_restores_previous_database_and_images(self):
        root,release,images=self.candidate()
        previous_image='ghcr.io/ecarara/speedtester-api@sha256:'+'b'*64
        state=json.loads((root/'deployment.json').read_text())
        state['images']['api']=previous_image
        deployment.save_json(root/'deployment.json',state)
        with patch.object(deployment,'release_source',return_value=release), \
             patch.object(deployment,'image_digests',return_value=images), \
             patch.object(deployment,'run') as execute, patch.object(deployment,'validate_policy'), \
             patch.object(deployment,'backup_database',return_value='snapshot.db') as snapshot, \
             patch.object(deployment,'restore_database') as restore, patch.object(deployment,'validate_service'), \
             patch.object(deployment,'staging_baseline',side_effect=RuntimeError('baseline rejected')):
            with self.assertRaisesRegex(RuntimeError,'baseline rejected'):
                deployment.deploy(root,'a'*40,'example','db','backups')
        self.assertEqual(snapshot.call_args.args[1],previous_image)
        self.assertEqual(restore.call_args.args[1],previous_image)
        self.assertIn(str(root/'deploy-previous.json'),execute.call_args.args)
        self.assertEqual(json.loads((root/'deployment.json').read_text())['revision'],'b'*40)

    def test_image_revision_mismatch_is_rejected_before_service_stop(self):
        image={'Config':{'Labels':{'org.opencontainers.image.revision':'wrong'}},'RepoDigests':[]}
        with patch.object(deployment,'run',side_effect=['',json.dumps([image])]):
            with self.assertRaises(ValueError):deployment.image_digests('a'*40)

    def test_validation_waits_for_real_collector_liveness(self):
        with patch.object(deployment,'run',side_effect=[RuntimeError('starting'),'ok']),patch.object(deployment.time,'sleep'):
            deployment.validate_service(('docker','compose'))
        with patch.object(deployment,'run',side_effect=RuntimeError('stale')),patch.object(deployment.time,'sleep'):
            with self.assertRaises(RuntimeError):deployment.validate_service(('docker','compose'))


class ObservationTests(IntegrationFixture):
    def test_report_excludes_future_slots_and_counts_discarded_traffic(self):
        now=datetime.now(timezone.utc)
        start_observation(self.store,self.settings)
        with self.store._connection() as conn:
            value=json.loads(conn.execute("SELECT value FROM schema_meta WHERE key='observation'").fetchone()[0])
            value['started_at']=(now-timedelta(days=2)).isoformat()
            conn.execute("UPDATE schema_meta SET value=? WHERE key='observation'",(json.dumps(value),))
        started=(now-timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.store.add_slots([MeasurementSlot(now.date().isoformat(),'manha',1,started,'fixture'),MeasurementSlot(now.date().isoformat(),'noite',2,(now+timedelta(hours=1)).isoformat(),'fixture')])
        slot=self.store.all_slots()[0]
        self.store.claim_slot(slot['id'])
        self.store.add_sample(Sample(started,download_mbps=900,slot_id=slot['id']))
        self.store.add_attempt(slot['id'],started,started,'discarded',None,{'transfer_bytes':100})
        self.store.add_attempt(slot['id'],started,started,'selected',None,{'transfer_bytes':200})
        self.store.add_attempt(slot['id'],started,started,'timeout',None,{})
        result=report(self.store,self.settings,14,now)
        self.assertEqual(result['observed_days'],2)
        self.assertEqual(result['due_slots'],1)
        self.assertEqual(result['completion_pct'],100)
        self.assertEqual(result['known_transfer_bytes'],300)
        self.assertEqual(result['unknown_transfer_attempts'],1)
        self.assertFalse(result['sla_evidence'])
        self.assertNotIn('target_fingerprint',result)
        original=result['observation_started_at']
        start_observation(self.store,self.settings)
        self.assertEqual(report(self.store,self.settings,14,now)['observation_started_at'],original)
