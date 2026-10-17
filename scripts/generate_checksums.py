#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Generate a deterministic SHA-256 manifest for release files."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    """Return the SHA-256 digest of a file without loading it all in memory."""
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Write SHA256SUMS for immediate files in a release directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", default="SHA256SUMS")
    args = parser.parse_args(argv)
    directory = args.directory
    if not directory.is_dir():
        parser.error(f"release directory does not exist: {directory}")
    output = directory / args.output
    files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path != output and path.name != "SHA256SUMS"
    )
    output.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in files),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
