# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Verify packaging orchestration and notices without compiling or downloading."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_desktop as build


class DesktopBuildTests(unittest.TestCase):
    def test_manifest_and_license_inventory_include_files_but_not_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'LICENSE').write_text('synthetic project license')
            bundle = root / 'bundle'
            bundle.mkdir()
            license_file = root / 'package/LICENSE.txt'
            license_file.parent.mkdir()
            license_file.write_text('synthetic dependency license')
            distribution = SimpleNamespace(metadata={'Name': 'fixture'}, version='1.0',
                files=[Path('LICENSE.txt'), Path('direct_url.json')], locate_file=lambda item: license_file.parent / item)
            with patch.object(build, 'ROOT', root), patch.object(build.metadata, 'distributions', return_value=[distribution]):
                build.notices(bundle)
            inventory = json.loads((bundle / 'runtime-components.json').read_text())
            self.assertEqual(inventory['components'], [{'name': 'fixture', 'version': '1.0'}])
            self.assertEqual((bundle / 'LICENSE').read_text(), 'synthetic project license')
            build.manifest(bundle)
            manifest = json.loads((bundle / 'bundle-manifest.json').read_text())
            self.assertIn('LICENSE', manifest['files'])
            self.assertNotIn('bundle-manifest.json', manifest['files'])
            self.assertFalse(any('direct_url' in name for name in manifest['files']))

    def test_build_orchestrates_each_platform_and_archives_the_exact_bundle(self):
        for system in ('Linux', 'Darwin', 'Windows'):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                target = root / 'dist/desktop/raw' / ('SpeedTesterClient.app' if system == 'Darwin' else 'SpeedTesterClient')
                def run(command, **_options):
                    if command[0] == 'git':
                        return SimpleNamespace(returncode=0, stdout='a' * 40)
                    if 'PyInstaller' in command:
                        target.mkdir(parents=True)
                        (target / 'runtime-components.json').write_text('{}')
                        (target / 'fixture').write_bytes(b'packaged fixture')
                    if command[0] == '/usr/bin/ditto':
                        Path(command[-1]).write_bytes(b'synthetic mac archive')
                    return SimpleNamespace(returncode=0)
                with patch.object(build, 'ROOT', root), patch.object(build.platform, 'system', return_value=system), \
                        patch.object(build, 'notices'), patch.object(build, '_linux_input_flags', return_value=[]), \
                        patch('bundle_iperf.build'), patch.object(build.subprocess, 'run', side_effect=run), \
                        patch.dict(build.os.environ, {'SOURCE_REVISION': ''}):
                    build.build()
                self.assertTrue((target / 'bundle-manifest.json').is_file())
                metadata = json.loads((target / 'build-info.json').read_text())
                self.assertEqual(metadata['revision'], 'a' * 40)
                manifests = list((root / 'dist/desktop/releases').glob('*.sha256'))
                self.assertEqual(len(manifests), 1)
                expected, name = manifests[0].read_text().strip().split('  ')
                self.assertEqual(build.checksum(manifests[0].parent / name), expected)

    def test_linux_input_payload_is_required_and_collects_only_existing_modules(self):
        original_path = Path
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            locale = root / 'locale'
            locale.mkdir()
            modules = root / 'lib/X11/locale'
            modules.mkdir(parents=True)
            (modules / 'fixture.so').write_bytes(b'synthetic XIM module')
            def fixture_path(value):
                return {'/usr/share/X11/locale': locale, '/usr/lib/X11/locale': modules,
                        '/usr/lib': root / 'lib'}.get(str(value), original_path(value))
            with patch.object(build, 'Path', side_effect=fixture_path):
                flags = build._linux_input_flags()
            self.assertIn('--add-data', flags)
            self.assertIn('--add-binary', flags)
            locale.rmdir()
            with patch.object(build, 'Path', side_effect=fixture_path):
                with self.assertRaisesRegex(RuntimeError, 'Xlib locale data required'):
                    build._linux_input_flags()
