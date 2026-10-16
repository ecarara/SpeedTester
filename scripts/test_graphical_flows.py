#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Run real widget/IPC workflows and preserve a machine-readable CI result."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'app'),str(ROOT/'tests')]
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_desktop_gui.py')
def test_ids(node):
    for child in node:
        if isinstance(child, unittest.TestSuite):
            yield from test_ids(child)
        else:
            yield child.id()

cases=list(test_ids(suite))
result=unittest.TextTestRunner(verbosity=2).run(suite)
report={'layer':'real Tk and authenticated IPC; signed synthetic Server; simulated OS elevation',
    'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
    'skipped':len(result.skipped),'checks':cases,'measurements':0}
directory=ROOT/'dist/desktop';directory.mkdir(parents=True,exist_ok=True)
(directory/'acceptance-gui.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(0 if result.wasSuccessful() and result.testsRun>=12 and not result.skipped else 1)
