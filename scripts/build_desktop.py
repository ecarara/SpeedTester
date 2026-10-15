#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Build an experimental native GUI bundle in an isolated public environment."""
import argparse
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(bundle):
    result = {"format": "cararalab-speedtester-desktop-v1", "files": {}}
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name != "bundle-manifest.json":
            result["files"][path.relative_to(bundle).as_posix()] = checksum(path)
    (bundle / "bundle-manifest.json").write_text(json.dumps(result, indent=2) + "\n")


def notices(bundle):
    packages = []
    for distribution in metadata.distributions():
        name, version = distribution.metadata["Name"], distribution.version
        packages.append({"name": name, "version": version})
        # Copy license files, never direct_url, environment paths or credentials.
        for item in distribution.files or ():
            if "licenses" not in item.parts and not item.name.lower().startswith(("license", "licence", "copying", "copyright")):
                continue
            source = distribution.locate_file(item)
            if not source.is_file():
                continue
            destination = bundle / "THIRD-PARTY-LICENSES" / name / (hashlib.sha256(str(item).encode()).hexdigest()[:8] + "-" + item.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    (bundle / "runtime-components.json").write_text(json.dumps({"scope": "build-environment; not a resolved runtime SBOM", "python": platform.python_version(),
        "components": sorted(packages, key=lambda item: item["name"].lower())}, indent=2) + "\n")
    shutil.copyfile(ROOT / "LICENSE", bundle / "LICENSE")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copyfile(python_license, bundle / "PYTHON-LICENSE.txt")


def build(smoke=True):
    output = ROOT / "dist/desktop"
    work = ROOT / "build/desktop"
    work.mkdir(parents=True, exist_ok=True)
    launcher = work / "launcher.py"
    launcher.write_text("from speedtester_protocol.desktop_entry import main\nraise SystemExit(main())\n")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "SpeedTesterClient", "--paths", str(ROOT / "app"),
        "--distpath", str(output / "raw"), "--workpath", str(work / "cache"), "--specpath", str(work)]
    if platform.system() in ("Windows", "Darwin"):
        command.append("--windowed")
    if platform.system() == "Darwin":
        command.extend(("--osx-bundle-identifier", "com.cararalab.speedtester.client"))
    if platform.system() == "Windows":
        command.extend(("--hidden-import", "win32timezone", "--hidden-import", "servicemanager"))
    subprocess.run([*command, str(launcher)], check=True, cwd=ROOT)
    system = platform.system()
    bundle = output / "raw" / ("SpeedTesterClient.app" if system == "Darwin" else "SpeedTesterClient")
    notices(bundle)
    (bundle / "PREVIEW.txt").write_text(
        "EXPERIMENTAL DEVELOPER PREVIEW — not a certified production installer.\n"
        "Native service lifecycle and iPerf3 distribution still require full native validation.\n"
        "Code signing/notarization, MSI/PKG/DEB/RPM integration and native uninstall registration are pending.\n"
        "Installation and pairing do not run measurements. The schedule starts disabled.\n"
        "The measurement tool is not bundled in this preview; do not enable it on a production workstation.\n")
    manifest(bundle)
    executable = bundle / ("Contents/MacOS/SpeedTesterClient" if system == "Darwin" else "SpeedTesterClient.exe" if system == "Windows" else "SpeedTesterClient")
    if smoke:
        with __import__("tempfile").TemporaryDirectory() as temporary:
            subprocess.run([str(executable), "--ui-smoke"], check=True, timeout=120, cwd=temporary)
    releases = output / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    name = "SpeedTesterClient-preview-" + system.lower() + "-" + platform.machine().lower()
    if system == "Darwin":
        archive = releases / (name + ".zip")
        subprocess.run(["/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(bundle), str(archive)], check=True)
    else:
        archive = Path(shutil.make_archive(str(releases / name), "zip" if system == "Windows" else "gztar",
            root_dir=bundle.parent, base_dir=bundle.name))
    archive.with_name(archive.name + ".sha256").write_text(checksum(archive) + "  " + archive.name + "\n")
    shutil.copyfile(bundle / "runtime-components.json", releases / (name + "-components.json"))
    print("experimental-native-bundle-ok: " + archive.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build()
