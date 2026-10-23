# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Coverage must include child processes without omitting application modules."""
import configparser
from pathlib import Path
import unittest


class CoveragePipelineTests(unittest.TestCase):
    def test_parallel_data_is_combined_before_reporting_in_both_workflows(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('ci.yml', 'sonarqube.yml'):
            with self.subTest(workflow=name):
                source = (root / '.github/workflows' / name).read_text()
                self.assertLess(source.index('coverage combine'), source.index('coverage xml'))
                self.assertNotIn('continue-on-error: true', source)

    def test_collection_keeps_all_source_directories_and_measures_subprocesses(self):
        root = Path(__file__).resolve().parents[1]
        configuration = configparser.ConfigParser()
        configuration.read(root / '.coveragerc')
        self.assertEqual(set(configuration['run']['source'].split()), {'app', 'scripts', 'security'})
        self.assertIn('subprocess', configuration['run']['patch'].split())
        self.assertNotIn('omit', configuration['run'])
        sonar = (root / '.github/workflows/sonarqube.yml').read_text()
        self.assertIn("SPEEDTESTER_GUI_TESTS: '1'", sonar)
        self.assertIn('sonar.qualitygate.wait=true', sonar)
