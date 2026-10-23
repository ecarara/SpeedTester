# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""No network or runners: fail-closed checks for the standalone installer."""
import argparse
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'install-speedtester-client.py'
SPEC = importlib.util.spec_from_file_location('community_bootstrap', SOURCE)
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.version = '0.4.9'

    def archive(self, extra=None):
        path = self.root / 'fixture.tar.gz'
        prefix = 'SpeedTester-' + self.version
        with tarfile.open(path, 'w:gz') as archive:
            for name in ('packaging/linux/install-user.sh', 'packaging/linux/configure-user.sh', 'app/requirements.txt',
                         'app/collector/target_selection.py', 'LICENSE'):
                info = tarfile.TarInfo(prefix + '/' + name)
                data = b'synthetic installation fixture\n'
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            if extra:
                archive.addfile(extra)
        return path

    def release(self, archive):
        archive_name = f'SpeedTester-{self.version}.tar.gz'
        archive_url = 'https://github.com/ecarara/SpeedTester/releases/download/v' + self.version + '/' + archive_name
        checksum_url = 'https://github.com/ecarara/SpeedTester/releases/download/v' + self.version + '/SHA256SUMS'
        return self.version, archive_name, archive_url, checksum_url

    def response(self, data, url):
        stream = io.BytesIO(data)
        stream.geturl = lambda: url
        return stream

    def opener(self, archive, checksums):
        def open_url(request, **kwargs):
            url = request.full_url
            return self.response(checksums if url.endswith('SHA256SUMS') else archive, url)
        return open_url

    def test_download_checks_digest_and_refuses_tampering_or_foreign_origin(self):
        data = self.archive().read_bytes()
        release = self.release(data)
        checksums = (hashlib.sha256(data).hexdigest() + '  ' + release[1] + '\n').encode()
        installer.download_archive(self.root / 'download.tar.gz', release, self.opener(data, checksums))
        tampered_opener = self.opener(data + b'changed', checksums)
        with self.assertRaises(installer.InstallationError):
            installer.download_archive(self.root / 'modified.tar.gz', release, tampered_opener)

        foreign = (release[0], release[1], 'http://codeload.github.com/archive', release[3])
        foreign_opener = self.opener(data, checksums)
        with self.assertRaises(installer.InstallationError):
            installer.download_archive(self.root / 'foreign.tar.gz', foreign, foreign_opener)

        with patch.object(installer, 'MAX_DOWNLOAD_BYTES', 1):
            oversized_opener = self.opener(data, checksums)
            with self.assertRaises(installer.InstallationError):
                installer.download_archive(self.root / 'oversized.tar.gz', release, oversized_opener)



    def test_complete_package_is_extracted_and_keeps_the_existing_installer(self):
        project = installer.extract_archive(self.archive(), self.root / 'source', self.version)
        self.assertTrue((project / 'packaging/linux/install-user.sh').is_file())
        self.assertTrue((project / 'app/collector/target_selection.py').is_file())

    def test_traversal_links_and_unpacking_limits_are_rejected_before_extraction(self):
        for name, kind in (('../escape', tarfile.REGTYPE),
                           ('SpeedTester-' + self.version + '/link', tarfile.SYMTYPE)):
            self.archive().unlink(missing_ok=True)
            extra = tarfile.TarInfo(name)
            extra.type = kind
            extra.linkname = '/etc/passwd'
            archive = self.archive(extra)
            with self.assertRaises(installer.InstallationError):
                installer.extract_archive(archive, self.root / 'source', self.version)
            self.assertFalse((self.root / 'source').exists())
        with patch.object(installer, 'MAX_UNPACKED_BYTES', 1):
            with self.assertRaises(installer.InstallationError):
                installer.extract_archive(self.root / 'fixture.tar.gz', self.root / 'large', self.version)

    def test_failed_verification_never_launches_installation_and_success_passes_server(self):
        release = self.release(b'')
        with patch.object(installer, 'check_requirements'), patch.object(installer, 'latest_release', return_value=release), patch.object(installer, 'download_archive', side_effect=installer.InstallationError('invalid')), patch.object(installer.subprocess, 'call') as child:
            with self.assertRaises(installer.InstallationError):
                installer.install('https://server.example')
            child.assert_not_called()
        project = self.root / 'package'
        with patch.object(installer, 'check_requirements'), patch.object(installer, 'latest_release', return_value=release), patch.object(installer, 'download_archive'), patch.object(installer, 'extract_archive', return_value=project), patch.object(installer.subprocess, 'call', return_value=0) as child:
            self.assertEqual(installer.install('measurement.example', 5300), 0)
            self.assertEqual(child.call_args.args[0], ['bash', str(project / 'packaging/linux/install-user.sh')])
            self.assertEqual(child.call_args.kwargs['env']['SPEEDTESTER_IPERF3_SERVER'], 'measurement.example')
            self.assertEqual(child.call_args.kwargs['env']['SPEEDTESTER_IPERF3_PORT'], '5300')

    def test_platform_and_server_origin_fail_closed_and_help_has_no_side_effects(self):
        with patch.object(installer.platform, 'system', return_value='Darwin'):
            with self.assertRaises(installer.InstallationError):
                installer.check_requirements()
        for origin in ('http://server.example', 'https://user:secret@server.example', 'https://server.example/path', 'https://server.example?x=1'):
            with self.assertRaises(argparse.ArgumentTypeError):
                installer.server_origin(origin)
        result = subprocess.run([sys.executable, str(SOURCE), '--help'], capture_output=True, text=True, check=True)
        self.assertIn('--server', result.stdout)


if __name__ == '__main__':
    unittest.main()
