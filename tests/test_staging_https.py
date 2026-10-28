# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise staging provisioning and deployment guards without host changes."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('staging_https', ROOT / 'scripts/staging_https.py')
staging = module_from_spec(spec)
spec.loader.exec_module(staging)
load_profile = staging.load_profile
deploy_spec = spec_from_file_location('deploy_https_test', ROOT / 'scripts/deploy.py')
deploy = module_from_spec(deploy_spec)
deploy_spec.loader.exec_module(deploy)


class StagingHttpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = self.root / '.env'
        self.env.write_text('API_PORT=8000\nSECRET=keep\n')
        self.deploy_config = self.root / 'deploy.conf'
        self.deploy_config.write_text('DEPLOY_ROOT=/opt/speedtester\n')
        self.nginx = self.root / 'nginx.conf'
        self.cert = self.root / 'cert'
        self.key = self.root / 'key'
        self.cert.write_text('fixture')
        self.key.write_text('fixture')
        self.template = self.root / 'template'
        self.template.write_text('nginx fixture')
        self.addCleanup(patch.stopall)
        self.profile = {'domain': 'staging.example.com', 'listen_address': '192.0.2.10',
                        'certificate': str(self.cert), 'private_key': str(self.key)}
        patch.object(staging, 'load_profile', return_value=self.profile).start()
        patch.object(staging, 'TEMPLATE', self.template).start()
        patch.object(staging.shutil, 'which', return_value=None).start()

    def fake_run(self, *args):
        if args == ('ss', '-ltn'):
            return ''
        if args == ('getenforce',):
            return 'Enforcing'
        if args == ('semanage', 'port', '-l'):
            return 'soundd_port_t tcp 8000\n'
        return ''

    def test_reinstall_provisions_proxy_env_and_security_configuration_idempotently(self):
        with patch.object(staging, 'run', side_effect=self.fake_run) as runner:
            staging.prepare(self.root, self.nginx, self.deploy_config)
            self.assertIn('API_PORT=18000\n', self.env.read_text())
            self.assertIn('API_BIND_ADDRESS=127.0.0.1\n', self.env.read_text())
            self.assertIn('API_COOKIE_SECURE=true\n', self.env.read_text())
            self.assertIn('SECRET=keep\n', self.env.read_text())
            self.assertIn('SPEEDTESTER_STAGING_HTTPS_CHECK=true\n', self.deploy_config.read_text())
            self.assertEqual(self.nginx.read_text(), 'nginx fixture')
            self.assertIn(('semanage', 'port', '-m', '-t', 'http_port_t', '-p', 'tcp', '8000'),
                          [call.args for call in runner.call_args_list])
        def already_configured(*args):
            if args == ('semanage', 'port', '-l'):
                return 'http_port_t tcp 8000\n'
            return self.fake_run(*args)
        with patch.object(staging, 'run', side_effect=already_configured) as runner:
            staging.prepare(self.root, self.nginx, self.deploy_config)
            self.assertNotIn('nginx', [call.args[0] for call in runner.call_args_list])

    def test_failed_nginx_validation_restores_all_files_and_selinux(self):
        original_env = self.env.read_text()
        original_deploy = self.deploy_config.read_text()
        def fail(*args):
            if args == ('nginx', '-t') and not self.nginx.exists():
                return ''
            if args == ('nginx', '-t'):
                raise RuntimeError('invalid configuration')
            return self.fake_run(*args)
        with patch.object(staging, 'run', side_effect=fail) as runner:
            with self.assertRaises(RuntimeError):
                staging.prepare(self.root, self.nginx, self.deploy_config)
        self.assertEqual(self.env.read_text(), original_env)
        self.assertEqual(self.deploy_config.read_text(), original_deploy)
        self.assertFalse(self.nginx.exists())
        self.assertIn(('semanage', 'port', '-d', '-p', 'tcp', '8000'),
                      [call.args for call in runner.call_args_list])

    def test_conflicting_custom_selinux_rule_is_not_overwritten(self):
        def conflict(*args):
            if args == ('semanage', 'port', '-l', '-C'):
                return 'other_port_t tcp 8000\n'
            return self.fake_run(*args)
        with patch.object(staging, 'run', side_effect=conflict):
            with self.assertRaisesRegex(RuntimeError, 'conflicting'):
                staging.prepare(self.root, self.nginx, self.deploy_config)
        self.assertFalse(self.nginx.exists())

    def test_host_profile_rejects_unsafe_nginx_input(self):
        path = self.root / 'profile.json'
        path.write_text(json.dumps(self.profile))
        path.chmod(0o600)
        self.assertEqual(load_profile(path), self.profile)
        for key, value in (('domain', 'example.com;include evil'), ('listen_address', '0.0.0.0'),
                           ('private_key', '/etc/../etc/key'), ('certificate', '/tmp/x;include')):
            path.write_text(json.dumps({**self.profile, key: value}))
            with self.assertRaises(ValueError):
                load_profile(path)

    def test_versioned_template_renders_proxy_and_preserves_nginx_variables(self):
        template = ROOT / 'ops/staging/nginx-https.conf.example'
        with patch.object(staging, 'TEMPLATE', template):
            config = staging.render(self.profile)
        self.assertIn('listen 192.0.2.10:8000;', config)
        self.assertIn('proxy_pass http://127.0.0.1:18000;', config)
        self.assertIn('https://staging.example.com$request_uri', config)
        self.assertIn('proxy_set_header X-Real-IP $remote_addr;', config)
        self.assertNotIn('${', config)

    def test_drift_stops_deploy_before_container_operations(self):
        with patch.dict(deploy.os.environ, {'SPEEDTESTER_STAGING_HTTPS_CHECK': 'true'}), \
             patch.object(deploy, 'run', side_effect=RuntimeError('proxy drift')) as runner:
            with self.assertRaisesRegex(RuntimeError, 'proxy drift'):
                deploy.deploy(self.root, 'a' * 40, 'example', 'db', 'backups')
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(runner.call_args.args[2], 'verify')

    @unittest.skipUnless(shutil.which('openssl'), 'openssl is required for the TLS fixture')
    def test_verify_uses_real_redirect_and_validated_https_health(self):
        self.env.write_text(staging.update_assignments(self.env.read_text(), staging.ENV_VALUES))
        self.nginx.write_text(self.template.read_text())
        certificate, key = self.root / 'server.pem', self.root / 'server.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(certificate), '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        class Handler(BaseHTTPRequestHandler):
            redirect = ''
            def do_GET(self):
                if self.path.startswith('/login'):
                    self.send_response(308)
                    self.send_header('Location', self.redirect + self.path)
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"status":"alive"}')
            def log_message(self, *args):
                pass
        http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        https = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(certificate, key)
        https.socket = tls.wrap_socket(https.socket, server_side=True)
        Handler.redirect = f'https://localhost:{https.server_port}'
        for server in (http, https):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        trusted = ssl.create_default_context(cafile=str(certificate))
        with patch.object(staging, 'urls', return_value=(f'http://127.0.0.1:{http.server_port}', Handler.redirect)), \
             patch('ssl._create_default_https_context', return_value=trusted):
            staging.verify(self.root, self.nginx)
            Handler.redirect = 'https://wrong.example'
            with self.assertRaisesRegex(RuntimeError, 'redirect'):
                staging.verify(self.root, self.nginx)


if __name__ == '__main__':
    unittest.main()
