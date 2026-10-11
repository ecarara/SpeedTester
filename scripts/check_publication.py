#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Check publishable files for local artifacts, private IPv4s and common secrets."""
from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SECRETS = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


def main() -> int:
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
    ).decode().split("\0")
    failures = []
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        if not path.is_file():
            continue
        if (path.name == ".env" or path.name.startswith(".env.")
                or path.suffix in {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".log"}
                or any(part in {"data", "backups", "__pycache__"} or part.startswith(".venv")
                       for part in path.relative_to(ROOT).parts)):
            failures.append(f"{name}: local artifact")
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        if SECRETS.search(text):
            failures.append(f"{name}: possible secret")
        # This script contains the network definitions used by the check.
        if name == "scripts/check_publication.py":
            continue
        for literal in IPV4.findall(text):
            try:
                address = ipaddress.ip_address(literal)
            except ValueError:
                continue
            if any(address in network for network in PRIVATE_NETWORKS):
                failures.append(f"{name}: private IPv4 literal")
                break
    if failures:
        print("Publication check failed (values intentionally omitted):")
        print("\n".join(failures))
        return 1
    print("publication-hygiene-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
