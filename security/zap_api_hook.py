# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Header applies only to the disposable API host; never to external origins."""


def zap_started(zap, target):
    # A private -dir starts without the packaged user's API scan policy.
    zap.ascan.import_scan_policy('/home/zap/.ZAP/policies/API-Minimal.policy')
    if 'API Minimal' not in zap.ascan.scan_policy_names:
        raise ValueError('The packaged API scan policy was not imported')
    zap.replacer.add_rule(description='synthetic API authentication', enabled='true',
        matchtype='REQ_HEADER', matchregex='false', matchstring='X-Admin-Token',
        replacement='security-fixture-admin', initiators='', url=r'^http://api:8000/.*')


def zap_active_scan(zap, target, policy):
    # Import uses the XML policy title, while the packaged script passes the
    # filename stem. Select the imported policy with the same unchanged rules.
    return zap, target, 'API Minimal'
