# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Trust failures and scan isolation; all fixtures are disposable and offline."""
from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import tarfile
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = spec_from_file_location(name, ROOT / path)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


deploy = module('security_deploy', 'scripts/deploy.py')
zap = module('security_zap', 'scripts/zap_scan.py')
grype = module('security_grype', 'scripts/check_image_report.py')
installer = module('security_installer', 'scripts/install_security_tools.py')


class InstallerTests(unittest.TestCase):
    def test_only_verified_binary_is_installed_and_archive_paths_are_not_extracted(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name in ('../../escaped', 'release/bin/gh'):
                member = tarfile.TarInfo(name)
                member.size = 6
                archive.addfile(member, io.BytesIO(b'binary'))
        payload = stream.getvalue()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'security').mkdir()
            asset = {'name': 'fixture.tar.gz', 'sha256': hashlib.sha256(payload).hexdigest()}
            manifest = {'gh': {'version': 'fixture', 'repository': 'cli/cli',
                               'archives': {'Linux-x86_64': asset}}}
            (root / 'security/tools.json').write_text(json.dumps(manifest))
            with patch.object(installer, 'ROOT', root), patch.object(installer.platform, 'system', return_value='Linux'), \
                 patch.object(installer.platform, 'machine', return_value='x86_64'), \
                 patch.object(installer.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(payload)):
                installer.install('gh', root / 'bin')
                self.assertEqual((root / 'bin/gh').read_bytes(), b'binary')
                self.assertEqual((root / 'bin/gh').stat().st_mode & 0o777, 0o755)
                self.assertFalse((root.parent / 'escaped').exists())
                asset['sha256'] = '0' * 64
                (root / 'security/tools.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    installer.install('gh', root / 'untrusted')
                self.assertFalse((root / 'untrusted').exists())

    def test_cli_installs_only_requested_tools(self):
        with patch.object(sys, 'argv', ['installer', 'gh', 'conftest', '--destination', '/tmp/fixture']), \
             patch.object(installer, 'install') as install:
            installer.main()
        self.assertEqual([call.args[0] for call in install.call_args_list], ['gh', 'conftest'])


class ImageGateTests(unittest.TestCase):
    def test_cli_blocks_bad_images_and_accepts_complete_clean_evidence(self):
        for blocking in (0, 1):
            with patch.object(sys, 'argv', ['gate', '/tmp/fixture.json']), \
                 patch.object(grype, 'check_report', return_value={'blocking_findings': blocking}):
                if blocking:
                    with self.assertRaises(SystemExit) as exit:
                        grype.main()
                    self.assertEqual(exit.exception.code, 1)
                else:
                    grype.main()
    def test_critical_always_blocks_and_high_requires_an_available_fix(self):
        cases = [('Critical', 'not-fixed', [], 1), ('Critical', 'fixed', ['2'], 1),
                 ('High', 'fixed', ['2'], 1), ('High', 'wont-fix', [], 0),
                 ('High', 'not-fixed', [], 0), ('Medium', 'fixed', ['2'], 0)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.json'
            for severity, state, versions, expected in cases:
                data = {'descriptor': {'db': {'status': {'valid': True}}}, 'matches': [
                    {'vulnerability': {'id': 'fixture-CVE', 'severity': severity,
                                       'fix': {'state': state, 'versions': versions}}}]}
                raw = json.dumps(data)
                path.write_text(raw)
                self.assertEqual(grype.check_report(path)['blocking_findings'], expected)
                self.assertEqual(path.read_text(), raw)

    def test_missing_report_evidence_and_invalid_database_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.json'
            for data in ({}, {'matches': [], 'descriptor': {'db': {'status': {'valid': False}}}}):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    grype.check_report(path)


class AttestationTests(unittest.TestCase):
    def test_policy_configuration_is_private_and_removed_after_verification(self):
        observed = []
        def execute(*args):
            if 'config' in args:
                return '{"private-example": "fixture"}'
            path = Path(args[2])
            observed.append(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn('--all-namespaces', args)
            self.assertEqual(json.loads(path.read_text())['private-example'], 'fixture')
            return ''
        with patch.object(deploy, 'run', side_effect=execute):
            deploy.validate_policy(('docker', 'compose'), ROOT)
        self.assertFalse(observed[0].exists())

    def test_baseline_uses_private_report_root_and_only_baseline_mode(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ,
                {'STAGING_BASELINE_URL': 'https://fixture.example.invalid/', 'SECURITY_REPORT_ROOT': temporary + '/reports'}), \
             patch.object(deploy, 'run') as execute:
            result = deploy.staging_baseline(ROOT, 'a' * 40)
            self.assertEqual(Path(result).parent.stat().st_mode & 0o777, 0o700)
            self.assertIn('baseline', execute.call_args.args)
            self.assertNotIn('active', execute.call_args.args)
        with patch.dict(os.environ, {'STAGING_BASELINE_URL': ''}):
            with self.assertRaises(ValueError):
                deploy.staging_baseline(ROOT, 'a' * 40)

    def test_github_response_is_bounded_and_invalid_digest_is_rejected(self):
        with patch.object(deploy.urllib.request, 'urlopen', return_value=io.BytesIO(b'{"safe":true}')):
            self.assertEqual(deploy.fetch_json('https://fixture.example.invalid/'), {'safe': True})
        with patch.object(deploy.urllib.request, 'urlopen', return_value=io.BytesIO(b'x' * (8 * 1024 * 1024 + 1))):
            with self.assertRaises(ValueError):
                deploy.fetch_json('https://fixture.example.invalid/')
        with self.assertRaises(ValueError):
            deploy.verify_attestation('image@sha256:invalid', 'a' * 40)
    def test_verifier_binds_digest_repo_source_ref_commit_and_workflow_without_token(self):
        image = 'ghcr.io/ecarara/speedtester-api@sha256:' + 'b' * 64
        with patch.object(deploy, 'fetch_json', return_value={'attestations': [{'bundle': {'example': 'signed-bundle'}}]}), \
             patch.object(deploy, 'run', return_value='[]') as execute:
            deploy.verify_attestation(image, 'a' * 40)
        args = execute.call_args.args
        self.assertIn('oci://' + image, args)
        for flag, value in (('--repo', deploy.REPO), ('--source-ref', 'refs/heads/main'),
                            ('--source-digest', 'a' * 40),
                            ('--signer-workflow', deploy.REPO + '/.github/workflows/images.yml')):
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertIn('--bundle', args)
        self.assertIn('--deny-self-hosted-runners', args)

    def test_forged_revision_label_is_insufficient_and_services_are_not_stopped(self):
        sha = 'a' * 40
        image = {'Config': {'Labels': {'org.opencontainers.image.revision': sha}},
                 'RepoDigests': ['ghcr.io/ecarara/speedtester-api@sha256:' + 'b' * 64]}
        with patch.object(deploy, 'run', side_effect=['', json.dumps([image])]) as execute, \
             patch.object(deploy, 'verify_attestation', side_effect=RuntimeError('untrusted signer')):
            with self.assertRaisesRegex(RuntimeError, 'untrusted signer'):
                deploy.image_digests(sha)
        self.assertFalse(any('stop' in call.args or 'up' in call.args for call in execute.call_args_list))

    def test_missing_attestation_is_fail_closed(self):
        with patch.object(deploy, 'fetch_json', return_value={'attestations': []}), patch.object(deploy, 'run') as execute:
            with self.assertRaisesRegex(ValueError, 'no build attestation'):
                deploy.verify_attestation('ghcr.io/ecarara/speedtester-api@sha256:' + 'b' * 64, 'a' * 40)
        execute.assert_not_called()

    def test_display_name_spoofing_does_not_approve_a_revision(self):
        sha = 'a' * 40
        runs = [{'id': i, 'head_sha': sha, 'name': name, 'path': '.github/workflows/untrusted.yml',
                 'event': 'push', 'head_branch': 'main', 'status': 'completed', 'conclusion': 'success'}
                for i, name in enumerate(deploy.REQUIRED)]
        with patch.object(deploy, 'fetch_json', side_effect=[{'commit': {'sha': sha}}, {'workflow_runs': runs}]):
            self.assertIsNone(deploy.eligible_revision())

    def test_remote_backup_overlay_survives_deploy_and_rollback(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {'BACKUP_REMOTE_ENABLED': 'true'}):
            root = Path(temporary)
            images = dict.fromkeys(deploy.SERVICES, 'sha256:' + 'a' * 64)
            for suffix in ('candidate', 'previous'):
                args = deploy.compose_command(root, root, images, 'fixture', 'db', 'backups', suffix)
                self.assertIn(str(root / 'docker/compose.backup-remote.yaml'), args)


class ZAPTests(unittest.TestCase):
    def test_active_scan_uses_fixed_target_and_disposable_data_then_cleans_up(self):
        project = 'speedtester-security-1-1'
        container = {'Config': {'Env': ['SPEEDTEST_SECURITY_FIXTURE=true', 'API_ADMIN_TOKEN=security-fixture-admin']},
                     'Mounts': [{'Destination': '/data', 'Type': 'volume', 'Name': project + '_fixture_data'}]}
        calls = []
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'scan'
            def execute(args, **kwargs):
                calls.append(args)
                if 'zap-api-scan.py' in args:
                    (output / 'zap.json').write_text(json.dumps({'site': [{'alerts': []}]}))
                return SimpleNamespace(returncode=0)
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), \
                 patch.object(zap, 'command', side_effect=[json.dumps([container]), json.dumps([{'Internal': True}]), '', '{}']), \
                 patch.object(zap.subprocess, 'run', side_effect=execute):
                self.assertEqual(zap.scan('active', output, project=project)['status'], 'passed')
            self.assertIn(project + '_isolated', calls[0])
            self.assertIn('/zap/wrk/openapi.json', calls[0])
            self.assertEqual(calls[-1][:3], ['docker', 'rm', '-f'])

    def test_failed_execution_cleans_up_and_does_not_accept_a_missing_report(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(zap.subprocess, 'run', return_value=SimpleNamespace(returncode=3)) as execute:
            with self.assertRaises(RuntimeError):
                zap.scan('baseline', Path(temporary) / 'scan', target='https://fixture.example.invalid/')
            self.assertEqual(execute.call_count, 2)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                zap.scan('baseline', Path(temporary) / 'scan', target='https://user:secret@fixture.example.invalid/')
    def test_active_scan_rejects_staging_and_non_ci_before_starting_docker(self):
        for environment, project in (({}, 'speedtester-security-1-1'), ({'GITHUB_ACTIONS': 'true'}, 'docker')):
            with patch.dict(os.environ, environment, clear=True), patch.object(zap, 'command') as command:
                with self.assertRaises(ValueError):
                    zap.verify_fixture(project)
                command.assert_not_called()

    def test_active_scan_rejects_shared_volume_and_external_network(self):
        container = {'Config': {'Env': ['SPEEDTEST_SECURITY_FIXTURE=true', 'API_ADMIN_TOKEN=security-fixture-admin']},
                     'Mounts': [{'Destination': '/data', 'Type': 'volume', 'Name': 'production_db'}]}
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), patch.object(zap, 'command', return_value=json.dumps([container])):
            with self.assertRaisesRegex(ValueError, 'disposable database'):
                zap.verify_fixture('speedtester-security-1-1')
        container['Mounts'][0]['Name'] = 'speedtester-security-1-1_fixture_data'
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}), patch.object(zap, 'command',
                side_effect=[json.dumps([container]), json.dumps([{'Internal': False}])]):
            with self.assertRaisesRegex(ValueError, 'isolated'):
                zap.verify_fixture('speedtester-security-1-1')

    def test_high_risk_alert_and_missing_report_block_the_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'zap.json'
            path.write_text(json.dumps({'site': [{'alerts': [{'riskcode': '3'}]}]}))
            with self.assertRaisesRegex(ValueError, 'high-risk'):
                zap.check_report(path)
            path.write_text(json.dumps({'site': [{'alerts': [{'riskcode': '2'}]}]}))
            self.assertEqual(zap.check_report(path)['status'], 'passed')
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'no target report'):
                zap.check_report(path)

    def test_staging_mode_invokes_only_packaged_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'report'
            calls = []
            def execute(args, **kwargs):
                calls.append(args)
                if 'zap-baseline.py' in args:
                    (output / 'zap.json').write_text(json.dumps({'site': [{'alerts': []}]}))
                return SimpleNamespace(returncode=0)
            with patch.object(zap.subprocess, 'run', side_effect=execute):
                result = zap.scan('baseline', output, target='http://fixture.example.invalid')
            self.assertEqual(result['status'], 'passed')
            self.assertIn('zap-baseline.py', calls[0])
            self.assertNotIn('zap-api-scan.py', calls[0])
            self.assertNotIn('--hook', calls[0])


if __name__ == '__main__':
    unittest.main()
