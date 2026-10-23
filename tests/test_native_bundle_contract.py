# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native packaging contracts with synthetic files; no compiler or network runs."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bundle_iperf as bundle


class NativeBundleTests(unittest.TestCase):
    def test_fetch_verifies_cached_and_downloaded_source_before_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'source.tar.gz'
            content = b'synthetic source fixture'
            entry = {'url': 'https://fixtures.invalid/source', 'sha256': hashlib.sha256(content).hexdigest()}
            with patch.object(bundle.urllib.request, 'urlopen', return_value=io.BytesIO(content)) as download:
                self.assertEqual(bundle.fetch(entry, path), path)
                download.assert_called_once()
            with patch.object(bundle.urllib.request, 'urlopen') as download:
                self.assertEqual(bundle.fetch(entry, path), path)
                download.assert_not_called()
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                bundle.fetch(entry, path)

    def test_native_build_preserves_sources_licenses_hashes_and_runtime_inventory(self):
        for system in ('Linux', 'Darwin', 'Windows'):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temporary:
                self.check_build(Path(temporary), system)

    def check_build(self, root, system):
        source = root / 'upstream/iperf-3.22'
        (source / 'src').mkdir(parents=True)
        (source / 'LICENSE').write_text('synthetic upstream license')
        for name in ('iperf3', 'iperf3.exe'):
            (source / 'src' / name).write_bytes(b'synthetic tool, never executed')
        archive = root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as package:
            package.add(source, arcname='iperf-3.22')
        crypto = root / 'crypto'
        crypto.mkdir()
        (crypto / 'LICENSE.txt').write_text('synthetic crypto license')
        library = crypto / ('libcrypto.3.dylib' if system == 'Darwin' else 'libcrypto.so.3')
        library.write_bytes(b'synthetic library')
        msys = root / 'msys'
        (msys / 'usr/bin').mkdir(parents=True)
        for name in ('msys-crypto-3.dll', 'msys-z.dll'):
            (msys / 'usr/bin' / name).write_bytes(b'synthetic dependency')
        (msys / 'usr/share/licenses/openssl').mkdir(parents=True)
        (msys / 'usr/share/licenses/openssl/LICENSE.txt').write_text('synthetic license')
        pins = {'version': '3.22', 'source': {'url': 'https://fixtures.invalid/iperf', 'sha256': 'fixture'},
                'windows_runtime': {'version': 'fixture', 'url': 'https://fixtures.invalid/runtime'},
                'windows_source': {'url': 'https://fixtures.invalid/runtime.src.tar.zst', 'sha256': 'fixture'}}
        (root / 'security').mkdir()
        (root / 'security/iperf3.json').write_text(json.dumps(pins))
        target = root / 'Bundle'
        target.mkdir()
        (target / 'runtime-components.json').write_text('{}')

        def fetch(entry, destination):
            if entry == pins['source']:
                shutil.copyfile(archive, destination)
            else:
                destination.write_bytes(b'synthetic pinned archive')
            return destination

        def run(command, **_options):
            joined = ' '.join(map(str, command))
            if '--prefix' in joined:
                return str(crypto)
            if 'otool' in joined:
                return 'fixture:\n' + str(library) + ' (compatibility version 3)'
            if command[0] == 'ldd':
                return 'libcrypto.so.3 => ' + str(library) + ' (0x00)'
            if 'objdump' in joined:
                return 'DLL Name: msys-2.0.dll\nDLL Name: msys-crypto-3.dll\nDLL Name: msys-z.dll'
            if 'tar --force-local' in joined:
                extraction = root / 'build/native-iperf/runtime'
                (extraction / 'usr/bin').mkdir(parents=True)
                (extraction / 'usr/bin/msys-2.0.dll').write_bytes(b'synthetic runtime')
                (extraction / 'usr/share/doc/Cygwin').mkdir(parents=True)
                (extraction / 'usr/share/doc/Cygwin/COPYING').write_text('synthetic license')
                return ''
            if 'openssl' in joined and 'version' in joined:
                return 'OpenSSL 3.6.0 fixture'
            return 'iperf 3.22 authentication'

        original_copy = shutil.copy2
        def copy_file(source_path, destination, **options):
            if str(source_path).startswith('/usr/share/doc/'):
                Path(destination).write_text('synthetic OS copyright')
                return destination
            return original_copy(source_path, destination, **options)

        with patch.object(bundle, 'ROOT', root), patch.object(bundle.platform, 'system', return_value=system), \
                patch.object(bundle, 'fetch', side_effect=fetch), patch.object(bundle, 'run', side_effect=run), \
                patch.object(bundle.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), \
                patch.object(bundle.shutil, 'copy2', side_effect=copy_file), \
                patch.dict(bundle.os.environ, {'SPEEDTESTER_MSYS_ROOT': str(msys)}):
            binary = bundle.build(target, '0.4.37')
        self.assertEqual(binary.read_bytes(), b'synthetic tool, never executed')
        inventory = json.loads((target / 'iperf-components.json').read_text())
        self.assertTrue(inventory['rsa_authentication'])
        for name, expected in inventory['files'].items():
            self.assertEqual(hashlib.sha256((binary.parent / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(len(inventory['components']), 3 if system == 'Windows' else 2)
        self.assertTrue((target / 'THIRD-PARTY-LICENSES/iperf3/iperf-3.22.tar.gz').is_file())
        self.assertIn('native_components', json.loads((target / 'runtime-components.json').read_text()))
        if system == 'Windows':
            self.assertIn('/v0.4.37/runtime.src.tar.zst', (target / 'THIRD-PARTY-LICENSES/MSYS2/SOURCE.txt').read_text())

    def test_unexpected_windows_dependency_is_rejected(self):
        tool, directory = Path('/fixture/iperf3.exe'), Path('/fixture')
        with patch.object(bundle, 'run', return_value='DLL Name: msys-unapproved.dll'):
            with self.assertRaisesRegex(ValueError, 'Unexpected native dependency'):
                bundle._copy_msys_dependencies(tool, directory, directory, directory, {})
