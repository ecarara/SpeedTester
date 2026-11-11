#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Opt-in lifecycle for the packaged frozen community agent."""

import json
import os
import pwd
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

BUNDLE = Path("/usr/lib/speedtester-agent/SpeedTesterClient")
BINARY = BUNDLE / "SpeedTesterClient"
STATE = Path("/var/lib/cararalab-speedtester-client")
BOOTSTRAP = STATE / "service.json"
SERVICE = "cararalab-speedtester-client.service"


def fail(message):
    print("speedtester-agent: " + message, file=sys.stderr)
    return 1


def require_root():
    if os.geteuid() != 0:
        raise PermissionError("execute com sudo")


def bootstrap_key():
    document = json.loads(BOOTSTRAP.read_text())
    key = document.get("control_key")
    if document.get("format") != "cararalab-speedtester-desktop-v1" or not isinstance(
        key, str
    ):
        raise ValueError("bootstrap inválido")
    return key


def invoke(operation, key):
    if not BINARY.is_file():
        raise FileNotFoundError("bundle do agente ausente")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir="/run", delete=False
    ) as stream:
        json.dump({"operation": operation, "control_key": key, "purge": False}, stream)
        request = Path(stream.name)
    os.chmod(request, 0o600)
    try:
        code = subprocess.run(
            [str(BINARY), "--native-helper", str(request)], check=False
        ).returncode
    finally:
        request.unlink(missing_ok=True)
    if code not in (0, 10):
        raise RuntimeError("native_operation_failed")
    return code


def write_user_control(key):
    user = os.environ.get("SUDO_USER", "")
    if not user or user == "root":
        return
    entry = pwd.getpwnam(user)
    home = Path(entry.pw_dir)
    config = home / ".config" / "cararalab"
    directory = config / "speedtester-client"
    for parent in (config, directory):
        parent.mkdir(parents=True, exist_ok=True)
        os.chown(parent, entry.pw_uid, entry.pw_gid)
    os.chmod(directory, 0o700)
    target = directory / "control.json"
    descriptor = os.open(
        target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump({"format": 1, "key": key}, stream)
        stream.write("\n")
    os.chown(target, entry.pw_uid, entry.pw_gid)


def enable(repair=False):
    require_root()
    existing = BOOTSTRAP.exists()
    key = bootstrap_key() if existing else secrets.token_hex(32)
    operation = "repair" if existing or repair else "install"
    code = invoke(operation, key)
    write_user_control(key)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now", SERVICE], check=False)
    active = subprocess.run(
        ["systemctl", "is-active", SERVICE], capture_output=True, text=True
    ).stdout.strip()
    print("speedtester-agent: " + operation + " concluído; serviço=" + active)
    if code == 10:
        print("speedtester-agent: reinicialização necessária")
    return 0


def disable():
    require_root()
    subprocess.run(["systemctl", "disable", "--now", SERVICE], check=False)
    print("speedtester-agent: compartilhamento desativado; dados preservados")
    return 0


def remove():
    require_root()
    if BOOTSTRAP.exists():
        invoke("uninstall", bootstrap_key())
    subprocess.run(["systemctl", "disable", SERVICE], check=False)
    print("speedtester-agent: runtime removido; dados preservados")
    return 0


def status():
    return subprocess.run(
        ["systemctl", "status", SERVICE, "--no-pager"], check=False
    ).returncode


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        if command == "enable":
            return enable()
        if command == "repair":
            return enable(repair=True)
        if command == "disable":
            return disable()
        if command == "remove":
            return remove()
        if command == "status":
            return status()
        return fail("uso: speedtester-agent enable|repair|disable|remove|status")
    except Exception as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
