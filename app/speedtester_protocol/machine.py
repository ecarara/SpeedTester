# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Origin-scoped pseudonym and signed central schedule, after consent/pairing.

OS identifiers never leave this function. This is not hardware attestation;
OS reinstallation, clones and a hostile administrator remain trust boundaries.
"""
import hashlib
import hmac
import platform
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4
from .client import ProtocolError, HTTPS
from .crypto import b64, public_bytes, sign, verify
from .desktop_links import system_environment
from .models import MachineReport, MachinePolicy

CAPABILITY = 'machine-schedule-v1'


def persistent_identifier():
    system = platform.system()
    try:
        if system == 'Linux':
            with Path('/etc/machine-id').open('r', encoding='ascii') as source:
                raw = source.read(129).strip().lower()
            if not re.fullmatch('[0-9a-f]{32}', raw):
                raise ValueError('invalid identifier')
            basis = 'linux-machine-id'
        elif system == 'Windows':
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                    0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                raw, kind = winreg.QueryValueEx(key, 'MachineGuid')
            if kind != winreg.REG_SZ:
                raise ValueError('invalid identifier')
            raw = UUID(raw).hex
            basis = 'windows-machine-guid'
        elif system == 'Darwin':
            result = subprocess.run(['/usr/sbin/ioreg', '-rd1', '-c', 'IOPlatformExpertDevice'],
                capture_output=True, timeout=10, check=True, env=system_environment())
            match = re.search(rb'"IOPlatformUUID"\s*=\s*"([0-9a-fA-F-]{36})"', result.stdout)
            if match is None:
                raise ValueError('missing identifier')
            raw = UUID(match.group(1).decode('ascii')).hex
            basis = 'macos-platform-uuid'
        else:
            raise ValueError('unsupported identifier')
        if raw in {'0'*32, 'f'*32}:
            raise ValueError('placeholder identifier')
        return basis, raw
    except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        raise ProtocolError('machine_identity_unavailable') from exc


def machine_identity(origin):
    parsed = urlsplit(HTTPS(origin).origin)
    scope = 'https://' + parsed.hostname.encode('idna').decode().lower()
    if parsed.port not in (None, 443):
        scope += ':' + str(parsed.port)
    basis, raw = persistent_identifier()
    payload = ('CararaLab-SpeedTester-machine-v1\0'+scope+'\0'+basis).encode('ascii')
    return {'machine_id': hmac.new(bytes.fromhex(raw), payload, hashlib.sha256).hexdigest(), 'basis': basis}


def sync_machine(credentials, measurement_key, config):
    if not credentials.bundle:
        raise ProtocolError('pairing_required')
    status, _, discovery = credentials.transport('GET', '/.well-known/speedtester-server', {}, None)
    if (status != 200 or not isinstance(discovery, dict) or discovery.get('protocol_version') != '1'
            or discovery.get('origin') != credentials.origin
            or discovery.get('signing_key') != b64(public_bytes(credentials.server_key))):
        raise ProtocolError('server_configuration_invalid')
    if CAPABILITY not in discovery.get('capabilities', []):
        return config
    scope = credentials.scope + ':machine'
    cached = credentials.queue.state(scope+':policy')
    if not cached:
        pending = credentials.queue.state(scope+':pending')
        if not pending:
            report = MachineReport(request_id=str(uuid4()), client_id=credentials.bundle.client_id,
                timezone=config['schedule']['timezone'], **machine_identity(credentials.origin))
            pending = report.model_dump()
            credentials.queue.state(scope+':pending', pending)
        reply = credentials.client().request('POST', '/api/v1/machine', sign(pending, measurement_key, 'machine-report-v1'))
        try:
            policy = MachinePolicy.model_validate(verify(reply, credentials.server_key, 'machine-policy-v1'))
            if ((policy.request_id, policy.client_id, policy.machine_id) !=
                    (pending['request_id'], pending['client_id'], pending['machine_id'])):
                raise ValueError('binding mismatch')
            from zoneinfo import ZoneInfo
            ZoneInfo(policy.timezone)
        except Exception as exc:
            raise ProtocolError('invalid_machine_policy') from exc
        cached = policy.model_dump()
        credentials.queue.put_batch([], scope, state_updates={scope+':policy':cached, scope+':pending':None})
    central = {'format':cached['format'], 'timezone':cached['timezone'], 'seed':cached['seed']}
    if config['schedule'] != central:
        config = {**config, 'schedule':central}
        credentials.queue.state('installation', config)
        # A new namespace preserves every old plan and cannot replay its slots.
        from .schedule import DailySchedule
        import time
        DailySchedule(credentials.queue, central).refresh(int(time.time()), activate=True)
    return config
