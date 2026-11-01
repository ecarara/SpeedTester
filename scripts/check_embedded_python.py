#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Reject embedded Python runtimes lacking the CVE-2026-115557 fix."""
import json
import re
import subprocess
import sys


def check(version, implementation):
    match = re.fullmatch(r"3\.14\.(\d+)", version)
    if implementation != "CPython" or not match or int(match.group(1)) < 10:
        raise ValueError("embedded runtime requires CPython 3.14.10 or newer in the 3.14 series")


def main():
    if len(sys.argv) == 1:
        check(".".join(map(str, sys.version_info[:3])), "CPython" if sys.implementation.name == "cpython" else "other")
    elif len(sys.argv) == 2:
        result = subprocess.run([sys.argv[1], "--runtime-info"], check=True,
                                capture_output=True, text=True, timeout=30)
        info = json.loads(result.stdout)
        if not info.get("frozen"):
            raise ValueError("expected a frozen executable")
        check(info.get("python", ""), info.get("implementation"))
    else:
        raise ValueError("expected zero arguments or one frozen executable")
    print("embedded-python-security-ok")


if __name__ == "__main__":
    main()
