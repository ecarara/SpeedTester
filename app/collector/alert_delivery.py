# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""At-least-once webhook outbox; recipients can deduplicate by stable alert ID."""
import json
import time
import urllib.error
import urllib.request


def deliver_due(store, webhook, now=None):
    if not webhook:
        return 0
    now = time.time() if now is None else now
    alerts = store.claim_alert_deliveries(now)
    for alert in alerts:
        payload = {key: alert[key] for key in ('id', 'created_at', 'kind', 'severity', 'message', 'payload')}
        request = urllib.request.Request(webhook, data=json.dumps(payload).encode(), method='POST',
            headers={'Content-Type': 'application/json', 'Idempotency-Key': f'speedtester-alert-{alert["id"]}'})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if not 200 <= response.status < 300:
                    raise ValueError('unexpected response status')
                response.read(1)
            store.finish_alert_delivery(alert['id'], True, now)
        except (OSError, ValueError) as exc:
            # A webhook URL may contain credentials; never persist the raw exception.
            detail = f'HTTP {exc.code}' if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            store.finish_alert_delivery(alert['id'], False, now, detail)
    return len(alerts)
