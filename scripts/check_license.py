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
    files.extend((ROOT / "install.sh", ROOT / "Makefile"))
    return sorted(set(files))


def main() -> int:
    """Validate license metadata and return a shell-friendly status code."""

    errors: list[str] = []
    license_path = ROOT / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8") if license_path.exists() else ""
    normalized_license = " ".join(license_text.split())
    for marker in REQUIRED_LICENSE_MARKERS:
        if marker not in normalized_license:
            errors.append(f"LICENSE is missing required GPL marker: {marker}")

    reuse_path = ROOT / "REUSE.toml"
    if not reuse_path.exists():
        errors.append("REUSE.toml is missing")
    else:
        reuse_text = reuse_path.read_text(encoding="utf-8")
        for marker in ("GPL-3.0-or-later", "Edson Angelo Carara", "version = 1"):
            if marker not in reuse_text:
                errors.append(f"REUSE.toml is missing: {marker}")

    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    for marker in ("Edson Angelo Carara", "ecarara/SpeedTester", "GPL-3.0-or-later"):
        if marker not in readme_text:
            errors.append(f"README.md is missing project metadata: {marker}")

    for path in source_files():
        text = path.read_text(encoding="utf-8")
        if "SPDX-License-Identifier: GPL-3.0-or-later" not in text:
            errors.append(f"{path.relative_to(ROOT)} is missing the GPL SPDX identifier")
        if "Copyright (C) 2026 Edson Angelo Carara" not in text:
            errors.append(f"{path.relative_to(ROOT)} is missing the copyright notice")

    if errors:
        print("license-check-failed")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"license-metadata-ok ({len(source_files())} source files checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
