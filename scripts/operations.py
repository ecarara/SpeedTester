#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Private operational checks, incident confirmation and durable notifications."""
import argparse
from datetime import datetime, timezone
from email.message import EmailMessage
import fcntl
import json
import os
from pathlib import Path
import shutil
import smtplib
import ssl
import subprocess
import time
import urllib.request

MESSAGES = {
    'https_failed': 'Acesso HTTPS indisponível ou certificado inválido.',
    'api_unavailable': 'API indisponível ou coletor sem heartbeat recente.',
    'samples_stale': 'Nenhuma nova amostra dentro da janela esperada.',
    'backup_stale': 'Backup ausente ou atrasado.',
    'disk_low': 'Espaço em disco abaixo do limite operacional.',
    'restarts': 'Um serviço reiniciou repetidamente ou está parado.',
    'deploy_blocked': 'Deploy bloqueado por falha ou espera prolongada nos gates.',
    'image_security': 'Reavaliação das imagens falhou ou está desatualizada.',
    'restore_failed': 'Teste de recuperação de backup falhou ou está atrasado.',
    'sync_failed': 'Cópia configurada para o OneDrive falhou ou está atrasada.',
}


def execute(args, payload=None):
    result = subprocess.run(args, input=payload, capture_output=True, text=True, timeout=300, check=False)
    if result.returncode:
        raise RuntimeError('Operational command failed; sensitive diagnostics withheld')
    return result.stdout.strip()


def private_json(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.chmod(0o600)
    os.replace(temporary, path)


def load_json(path):
    return json.loads(path.read_text()) if path.exists() else {}


def api_facts(project):
    code = """import json,os,sqlite3,urllib.request
from contextlib import closing
request=urllib.request.Request('http://127.0.0.1:8000/health',headers={'X-Admin-Token':os.environ.get('API_ADMIN_TOKEN','')})
health=json.load(urllib.request.urlopen(request,timeout=5))
with closing(sqlite3.connect('file:/data/speedtester.db?mode=ro',uri=True)) as db:
    latest=db.execute('SELECT MAX(started_at) FROM samples').fetchone()[0]
print(json.dumps({'collector_ok':health.get('collector',{}).get('status')=='ok','latest_sample':latest}))"""
    return json.loads(execute(['docker', 'exec', project + '-api-1', 'python', '-c', code]))


def container_facts(project):
    names = [project + '-' + name + '-1' for name in ('api', 'collector', 'backup', 'db')]
    data = json.loads(execute(['docker', 'inspect', *names]))
    return {item['Name']: {'running': item['State']['Running'], 'restarts': item['RestartCount'],
                           'id': item['Id']} for item in data}


def backup_command(state, volume, *command, outbox=None):
    args = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges:true', '--memory', '512m', '--cpus', '1',
            '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,noexec,size=268435456,mode=1777',
            '-v', volume + ':/backups:ro']
    if outbox:
        args.extend(['-v', str(outbox) + ':/exports:Z'])
    return args + [state['images']['backup'], *command]


def backup_facts(state, volume):
    code = "import json;from pathlib import Path;p=Path('/backups/.last-success.json');print(p.read_text() if p.exists() else '{}')"
    return json.loads(execute(backup_command(state, volume, 'python', '-c', code)))


def age(value, now):
    if not value:
        return float('inf')
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    return max(0, now - value)


def collect(root, project, volume, state_dir, now):
    state = load_json(root / 'deployment.json')
    facts = {'api_unavailable': True, 'samples_stale': False, 'restarts': True, 'backup_stale': True}
    try:
        api = api_facts(project)
        facts['api_unavailable'] = not api['collector_ok']
        facts['samples_stale'] = age(api['latest_sample'], now) > int(os.environ.get('SAMPLE_MAX_AGE_SECONDS', '28800'))
    except (RuntimeError, ValueError, KeyError):
        pass
    try:
        containers = container_facts(project)
        facts['restarts'] = restart_problem(containers, state_dir, now)
        backup = backup_facts(state, volume)
        facts['backup_stale'] = age(backup.get('completed_at'), now) > int(os.environ.get('BACKUP_MAX_AGE_SECONDS', '93600'))
    except (RuntimeError, ValueError, KeyError):
        pass
    disk = shutil.disk_usage(root)
    facts['disk_low'] = disk.free < int(os.environ.get('DISK_MIN_FREE_BYTES', str(5 * 1024**3))) or disk.free / disk.total < 0.1
    facts.update(report_facts(root, state_dir, now))
    if os.environ.get('HTTPS_HEALTH_URL'):
        facts['https_failed'] = not https_health()
    return facts


def https_health():
    try:
        context = ssl.create_default_context(cafile=os.environ.get('HTTPS_CA_FILE') or None)
        with urllib.request.urlopen(os.environ['HTTPS_HEALTH_URL'], context=context, timeout=15) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def restart_problem(containers, state_dir, now):
    previous = load_json(state_dir / 'containers.json')
    for name, item in containers.items():
        old = previous.get(name, {})
        changes = max(0, item['restarts'] - old.get('restarts', 0))
        if item['id'] != old.get('id'):
            changes = item['restarts']
        window = [stamp for stamp in old.get('window', []) if now - stamp < 3600]
        item['window'] = (window + [now] * min(changes, 100))[-100:]
    private_json(state_dir / 'containers.json', containers)
    return any(not item['running'] or len(item['window']) >= 3 for item in containers.values())


def report_facts(root, state_dir, now):
    deployment = load_json(root / '.deploy-status.json')
    facts = {'deploy_blocked': deployment.get('status') == 'failed' or (
        deployment.get('status') == 'waiting' and age(deployment.get('since'), now) > 7200)}
    for key, filename, max_age in (('image_security', 'images.json', 8 * 86400),
                                    ('restore_failed', 'restore.json', 8 * 86400)):
        report = load_json(state_dir / filename)
        facts[key] = report.get('status') != 'passed' or age(report.get('checked_at'), now) > max_age
    if os.environ.get('ONEDRIVE_REMOTE'):
        report = load_json(Path(os.environ['BACKUP_OUTBOX']) / '.sync-status.json')
        facts['sync_failed'] = report.get('status') != 'passed' or age(report.get('checked_at'), now) > 93600
    return facts


def incidents(previous, facts, now, confirmations=3, cooldown=21600):
    events = []
    result = {}
    for key, failed in facts.items():
        old = previous.get(key, {})
        count = old.get('failures', 0) + 1 if failed else 0
        active = count >= confirmations
        last_sent = old.get('last_sent', 0)
        if active and (not old.get('active') or now - last_sent >= cooldown):
            events.append({'kind': 'ops_' + key, 'message': MESSAGES[key], 'severity': 'critical', 'created_at': now})
            last_sent = now
        if not failed and old.get('active'):
            events.append({'kind': 'ops_recovered', 'message': 'Normalizado: ' + MESSAGES[key],
                           'severity': 'info', 'created_at': now})
        result[key] = {'failures': count, 'active': active, 'last_sent': last_sent}
    return result, events


def dashboard_delivery(project, event):
    code = """import json,os,sys
from api.store import SampleStore
event=json.load(sys.stdin)
store=SampleStore(os.environ['DB_PATH'])
try:
    store.add_alert(event['kind'],event['message'],severity=event['severity'],cooldown_seconds=0,
                    payload={'source':'host-monitor','observed_at':event['created_at']})
finally:
    store.close()"""
    execute(['docker', 'exec', '-i', project + '-api-1', 'python', '-c', code], json.dumps(event))


def email_delivery(event):
    recipient = os.environ.get('ALERT_EMAIL_TO', '')
    if not recipient:
        return
    message = EmailMessage()
    message['From'] = os.environ['ALERT_EMAIL_FROM']
    message['To'] = recipient
    message['Subject'] = 'SpeedTester: ' + ('recuperação' if event['severity'] == 'info' else 'alerta operacional')
    observed = datetime.fromtimestamp(event['created_at'], timezone.utc).isoformat()
    message.set_content(event['message'] + '\nObservado em: ' + observed + '\nConsulte o dashboard para detalhes.')
    host = os.environ['SMTP_HOST']
    port = int(os.environ.get('SMTP_PORT', '587'))
    context = ssl.create_default_context()
    connection = smtplib.SMTP_SSL(host, port, timeout=15, context=context) if port == 465 else smtplib.SMTP(host, port, timeout=15)
    with connection as smtp:
        if port != 465:
            smtp.starttls(context=context)
        username = os.environ.get('SMTP_USER')
        if username:
            password_file = Path(os.environ['SMTP_PASSWORD_FILE'])
            if password_file.is_symlink() or password_file.stat().st_mode & 0o077:
                raise OSError('SMTP password file must be private')
            smtp.login(username, password_file.read_text().strip())
        smtp.send_message(message)


def deliver_event(project, event):
    failed = False
    for channel, delivery in (('dashboard', lambda: dashboard_delivery(project, event)),
                               ('email', lambda: email_delivery(event))):
        key = channel + '_delivered'
        if event.get(key):
            continue
        try:
            delivery()
            event[key] = True
        except (OSError, RuntimeError, KeyError, smtplib.SMTPException):
            failed = True
    return failed


def deliver(project, queue, now):
    pending = []
    for event in queue:
        if event.get('retry_at', 0) > now:
            pending.append(event)
            continue
        if deliver_event(project, event):
            event['attempts'] = event.get('attempts', 0) + 1
            event['retry_at'] = now + min(21600, 60 * 2 ** min(event['attempts'], 8))
            pending.append(event)
    return pending[-100:]


def monitor(root, project, volume, state_dir, now=None):
    now = time.time() if now is None else now
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = state_dir / 'monitor.json'
    previous = load_json(path)
    facts = collect(root, project, volume, state_dir, now)
    current, events = incidents(previous.get('incidents', {}), facts, now)
    queue = previous.get('pending', []) + events
    # Persist before delivery so process restarts preserve pending incidents.
    private_json(path, {'checked_at': now, 'incidents': current, 'pending': queue[-100:]})
    pending = deliver(project, queue[-100:], now)
    private_json(path, {'checked_at': now, 'incidents': current, 'pending': pending})
    return {'status': 'degraded' if any(facts.values()) else 'passed', 'new_events': len(events), 'pending': len(pending)}


def recovery(root, volume, state_dir, outbox):
    state = load_json(root / 'deployment.json')
    outbox.mkdir(mode=0o700, parents=True, exist_ok=True)
    evidence = {'status': 'failed', 'checked_at': time.time()}
    try:
        name = execute(backup_command(state, volume, 'python', '/opt/speedtester-scripts/export_backup.py',
                                      '--source', '/backups', '--destination', '/exports', outbox=outbox))
        result = execute(backup_command(state, volume, 'python', '/opt/speedtester-scripts/check_restore.py', '/backups/' + name))
        evidence.update(json.loads(result.splitlines()[-1]))
        evidence['snapshot'] = name
        return evidence
    finally:
        private_json(state_dir / 'restore.json', evidence)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('monitor', 'recovery'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--project', default='speedtester')
    parser.add_argument('--backup-volume', required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--outbox', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (args.root / '.deployment.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if args.mode == 'monitor':
            result = monitor(args.root, args.project, args.backup_volume, args.state_dir)
        else:
            if not args.outbox:
                parser.error('--outbox is required for recovery')
            result = recovery(args.root, args.backup_volume, args.state_dir, args.outbox)
        print(json.dumps(result))


if __name__ == '__main__':
    main()
