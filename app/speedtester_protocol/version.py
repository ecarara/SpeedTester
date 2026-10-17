# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Public build identity. Diagnostics intentionally omit account/host secrets."""
import platform
import re

CLIENT_VERSION = '0.3.0.dev14'
BUILD_REVISION = 'source'


def set_build_revision(value):
    global BUILD_REVISION
    if value!='source' and not re.fullmatch('[0-9a-f]{40}',value):
        raise ValueError('invalid_build_revision')
    BUILD_REVISION=value


def build_label():
    return CLIENT_VERSION+' · '+BUILD_REVISION[:12]


def diagnostic_text(service=None):
    lines=['SpeedTester Client '+CLIENT_VERSION,'Build: '+BUILD_REVISION,
        'Platform: '+platform.system()+' / '+platform.machine()]
    if service:
        lines.extend(['Service: '+str(service.get('client_version','unknown')),
            'Service build: '+str(service.get('build_revision','unknown'))])
    return '\n'.join(lines)
