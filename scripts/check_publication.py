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
# Private IPv4 ranges expressed as integers to avoid hardcoded address literals.
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network((int(network), prefix))
    for network, prefix in ((0x0A000000, 8), (0xAC100000, 12), (0xC0A80000, 16))
)
LOCAL_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".pem", ".key", ".log"}
LOCAL_PARTS = {"data", "backups", "__pycache__"}
LOCAL_ARTIFACT = "local artifact"
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SECRETS = re.compile(
    r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{32,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)


def _listed_paths() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
    ).decode()
    return output.split("\0")


def _artifact_reason(path: Path) -> str | None:
    if path.name == ".env" or path.name.startswith(".env."):
        return LOCAL_ARTIFACT
    if path.suffix in LOCAL_SUFFIXES:
        return LOCAL_ARTIFACT
    for part in path.relative_to(ROOT).parts:
        if part in LOCAL_PARTS or part.startswith(".venv"):
            return LOCAL_ARTIFACT
    return None


def _has_private_ipv4(text: str) -> bool:
    for literal in IPV4.findall(text):
        try:
            address = ipaddress.ip_address(literal)
        except ValueError:
            continue
        if any(address in network for network in PRIVATE_NETWORKS):
            return True
    return False


def _scan_file(path: Path, name: str) -> str | None:
    reason = _artifact_reason(path)
    if reason:
        return reason
    data = path.read_bytes()
    if b"\0" in data:
        return None
    text = data.decode("utf-8", errors="replace")
    if SECRETS.search(text):
        return "possible secret"
    # This script contains the network definitions used by the check.
    if name == "scripts/check_publication.py":
        return None
    if _has_private_ipv4(text):
        return "private IPv4 literal"
    return None


def main() -> int:
    paths = _listed_paths()
    failures = []
    for name in sorted(set(paths) - {""}):
        path = ROOT / name
        if not path.is_file():
            continue
        reason = _scan_file(path, name)
        if reason:
            failures.append(f"{name}: {reason}")
    if failures:
        print("Publication check failed (values intentionally omitted):")
        print("\n".join(failures))
        return 1
    print("publication-hygiene-ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
