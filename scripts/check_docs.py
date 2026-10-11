#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Validate relative Markdown links that point inside this repository."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_SCHEMES = {"http", "https", "mailto", "tel"}


def main() -> int:
    """Return non-zero when a local Markdown link has no target."""
    root = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    markdown_files = sorted(root.rglob("*.md"))
    for document in markdown_files:
        if ".git" in document.parts or any(part.startswith(".venv") for part in document.parts):
            continue
        content = document.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(content):
            target = raw_target.strip().split("#", 1)[0].split("?", 1)[0]
            if not target or urlsplit(target).scheme in SKIP_SCHEMES:
                continue
            candidate = (document.parent / target).resolve()
            if not candidate.exists():
                failures.append(f"{document.relative_to(root)} -> {raw_target}")
    if failures:
        print("Broken documentation links:", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"documentation-links-ok ({len(markdown_files)} markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
