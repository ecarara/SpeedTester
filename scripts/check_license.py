#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Check the repository's basic, machine-verifiable GPL metadata.

This is a repository hygiene check, not a legal opinion. It catches accidental
omission of the license file or ownership metadata from project source files.
Third-party license compatibility still requires human review.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_LICENSE_MARKERS = (
    "GNU GENERAL PUBLIC LICENSE",
    "either version 3 of the License, or (at your option) any later version.",
    "END OF TERMS AND CONDITIONS",
)
SOURCE_ROOTS = (ROOT / "app", ROOT / "scripts", ROOT / "tests")
SOURCE_SUFFIXES = {".py", ".sh", ".html", ".cjs", ".js"}


def source_files() -> list[Path]:
    """Return owned executable/source files that must carry SPDX metadata."""

    files = [
        path
        for source_root in SOURCE_ROOTS
        for path in source_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.startswith(".venv") for part in path.parts)
        and path.suffix in SOURCE_SUFFIXES
    ]
    files.extend(
        path
        for path in (ROOT / "docker").rglob("*")
        if path.is_file() and (path.name.startswith("Dockerfile") or path.name.endswith(".yaml"))
    )
    files.extend((ROOT / "install.sh", ROOT / "install-community.sh", ROOT / "Makefile"))
    return sorted(set(files))


def _license_errors() -> list[str]:
    license_path = ROOT / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8") if license_path.exists() else ""
    normalized_license = " ".join(license_text.split())
    return [
        f"LICENSE is missing required GPL marker: {marker}"
        for marker in REQUIRED_LICENSE_MARKERS
        if marker not in normalized_license
    ]


def _reuse_errors() -> list[str]:
    reuse_path = ROOT / "REUSE.toml"
    if not reuse_path.exists():
        return ["REUSE.toml is missing"]
    reuse_text = reuse_path.read_text(encoding="utf-8")
    return [
        f"REUSE.toml is missing: {marker}"
        for marker in ("GPL-3.0-or-later", "Edson Angelo Carara", "version = 1")
        if marker not in reuse_text
    ]


def _readme_errors() -> list[str]:
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    return [
        f"README.md is missing project metadata: {marker}"
        for marker in ("Edson Angelo Carara", "ecarara/SpeedTester", "GPL-3.0-or-later")
        if marker not in readme_text
    ]


def _source_errors() -> list[str]:
    errors = []
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        if "SPDX-License-Identifier: GPL-3.0-or-later" not in text:
            errors.append(f"{path.relative_to(ROOT)} is missing the GPL SPDX identifier")
        if "Copyright (C) 2026 Edson Angelo Carara" not in text:
            errors.append(f"{path.relative_to(ROOT)} is missing the copyright notice")
    return errors


def main() -> int:
    """Validate license metadata and return a shell-friendly status code."""

    errors = _license_errors() + _reuse_errors() + _readme_errors() + _source_errors()
    if errors:
        print("license-check-failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"license-metadata-ok ({len(source_files())} source files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
