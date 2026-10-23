#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Validate the contents and checksums of SpeedTester release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
from zipfile import ZipFile


def sha256(path: Path) -> str:
    """Calculate a file digest in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command_output(command: list[str]) -> str:
    """Run a package inspection command and return its output."""
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)


def require_tokens(label: str, content: str, tokens: tuple[str, ...]) -> None:
    """Require every expected path or marker in a package listing."""
    missing = [token for token in tokens if token not in content]
    if missing:
        raise ValueError(f"{label} missing: {', '.join(missing)}")


def validate_checksums(directory: Path) -> None:
    """Verify every entry listed by SHA256SUMS."""
    manifest = directory / "SHA256SUMS"
    if not manifest.is_file():
        raise ValueError("SHA256SUMS is missing")
    entries = [line.split("  ", 1) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not entries:
        raise ValueError("SHA256SUMS is empty")
    for expected, name in entries:
        path = directory / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {name}")


def validate_source_archive(path: Path) -> None:
    """Check that source archive contains the public project contract."""
    with tarfile.open(path, "r:gz") as archive:
        names = archive.getnames()
    require_tokens(path.name, "\n".join(names), ("/LICENSE", "/README.md", "/app/", "/docs/"))
    forbidden = ("/.env", "/data/", "/backups/", ".db")
    if any(token in name for name in names for token in forbidden):
        raise ValueError(f"private data found in {path.name}")


def validate_spdx(path: Path) -> None:
    """Check required SPDX fields and the SpeedTester package."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("spdxVersion") != "SPDX-2.3":
        raise ValueError(f"{path.name} is not SPDX-2.3")
    packages = document.get("packages", [])
    if not any(package.get("name") == "SpeedTester" for package in packages):
        raise ValueError(f"{path.name} does not describe SpeedTester")


def validate_zip(path: Path) -> None:
    """Validate MSIX or macOS zip bundle contents without executing them."""
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        if path.suffix == ".msix":
            require_tokens(path.name, "\n".join(names), (
                "AppxManifest.xml",
                "SpeedTesterLauncher.exe",
                "SpeedTesterClient.exe",
                "Assets/Square44x44Logo.png",
                "Assets/Square150x150Logo.png",
            ))
            manifest = archive.read("AppxManifest.xml")
            if b"ecarara.SpeedTester" not in manifest:
                raise ValueError(f"{path.name} has an unexpected package identity")
        else:
            require_tokens(path.name, "\n".join(names), (
                "SpeedTester.app/Contents/Info.plist",
                "SpeedTester.app/Contents/MacOS/SpeedTesterLauncher",
                "SpeedTester.app/Contents/MacOS/SpeedTesterClient",
                "SpeedTester.app/Contents/Resources/SpeedTester.icns",
            ))


def validate_native_package(path: Path) -> None:
    """Inspect package file lists using the native package manager tools."""
    if path.suffix == ".deb":
        listing = command_output(["dpkg-deb", "--contents", str(path)])
    elif path.suffix == ".rpm":
        listing = command_output(["rpm", "-qlp", str(path)])
    else:
        return
    require_tokens(path.name, listing, (
        "speedtester.desktop",
        "speedtester-api.service",
        "speedtester-client.service",
        "speedtester-launcher",
    ))


def validate_pacman_package(path: Path) -> None:
    """Inspect an Arch package as a zstd-compressed tar archive."""
    listing = command_output(["tar", "--zstd", "-tf", str(path)])
    require_tokens(path.name, listing, (
        "usr/share/applications/speedtester.desktop",
        "usr/lib/systemd/user/speedtester-api.service",
        "usr/lib/systemd/user/speedtester-client.service",
        "usr/bin/speedtester-launcher",
    ))


def validate_artifact(artifact: Path) -> None:
    """Dispatch validation for one supported release artifact."""
    if artifact.name.endswith(".tar.gz"):
        validate_source_archive(artifact)
    elif artifact.name.endswith(".spdx.json"):
        validate_spdx(artifact)
    elif artifact.suffix in {".deb", ".rpm"}:
        validate_native_package(artifact)
    elif artifact.name.endswith(".pkg.tar.zst"):
        validate_pacman_package(artifact)
    elif artifact.suffix == ".flatpak" and artifact.stat().st_size == 0:
        raise ValueError(f"empty Flatpak bundle: {artifact.name}")
    elif artifact.suffix in {".msix", ".zip"}:
        validate_zip(artifact)
    elif artifact.suffix == ".dmg" and artifact.stat().st_size == 0:
        raise ValueError(f"empty disk image: {artifact.name}")


def main(argv: list[str] | None = None) -> int:
    """Validate all supported release files in a directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    directory = args.directory
    if not directory.is_dir():
        parser.error(f"release directory does not exist: {directory}")
    validate_checksums(directory)
    artifacts = sorted(path for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    if not artifacts:
        raise ValueError("release directory has no artifacts")
    for artifact in artifacts:
        validate_artifact(artifact)
    print(f"release-artifacts-ok ({len(artifacts)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
