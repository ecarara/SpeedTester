# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Header applies only to the disposable API host; never to external origins."""


def zap_started(zap, target):
    zap.replacer.add_rule(description='synthetic API authentication', enabled='true',
        matchtype='REQ_HEADER', matchregex='false', matchstring='X-Admin-Token',
        replacement='security-fixture-admin', initiators='', url=r'^http://api:8000/.*')
