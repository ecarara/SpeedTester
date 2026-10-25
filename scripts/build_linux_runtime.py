#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Freeze the Linux package runtime without copying a build-machine venv.

Build on the oldest supported glibc distribution; PyInstaller does not bundle
glibc. The resulting directory is shared by the DEB and RPM payload builders.
"""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ENTRIES = {"SpeedTesterAPI": "native_api_entry.py",
           "SpeedTesterClient": "native_client_entry.py",
           "SpeedTesterLauncher": "desktop_launcher.py"}


def check_environment():
    if (platform.system() != "Linux" or sys.implementation.name != "cpython"
            or sys.version_info[:2] != (3, 14)):
        raise ValueError("build with CPython 3.14 on the target Linux architecture")
    if metadata.version("pyinstaller") != "6.22.3":
        raise ValueError("PyInstaller 6.22.3 is required")
    name, version = platform.libc_ver()
    if name != "glibc" or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise ValueError("a glibc Linux build host is required")


def copy_notices(output):
    components = []
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        components.append({"name": name, "version": distribution.version})
        for item in distribution.files or ():
            if ("licenses" not in item.parts and not item.name.lower().startswith(
                    ("license", "licence", "copying", "copyright"))):
                continue
            source = distribution.locate_file(item)
            if source.is_file():
                filename = hashlib.sha256(str(item).encode()).hexdigest()[:8] + "-" + item.name
                destination = output / "THIRD-PARTY-LICENSES" / name / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
    python_licenses = (Path(sys.base_prefix) / "LICENSE.txt",
                       Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
                       Path(sys.base_prefix) / "share/doc/python3.14/copyright")
    for source in python_licenses:
        if source.is_file():
            shutil.copyfile(source, output / "PYTHON-LICENSE.txt")
            break
    else:
        raise ValueError("Python LICENSE.txt is missing from the build installation")
    shutil.copyfile(ROOT / "LICENSE", output / "LICENSE")
    return sorted(components, key=lambda item: item["name"].lower())


def verify_runtime(output, version):
    output = Path(output).resolve(strict=True)
    document = json.loads((output / "runtime-components.json").read_text())
    if (document.get("format") != "speedtester-linux-runtime-v1"
            or document.get("app_version") != version
            or not document.get("python", "").startswith("3.14.")
            or document.get("architecture") != platform.machine()
            or document.get("libc", {}).get("name") != "glibc"
            or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", document["libc"].get("version", ""))):
        raise ValueError("runtime version, architecture or glibc metadata does not match")
    # PyInstaller uses relative symlinks inside an onedir tree. A copied venv's
    # absolute interpreter link or any other link outside the payload is invalid.
    for path in output.rglob("*"):
        if path.is_symlink() and not path.resolve(strict=True).is_relative_to(output):
            raise ValueError("runtime symlink escapes the package: " + str(path))
        if path.name == "pyvenv.cfg":
            raise ValueError("a host virtual environment must not enter the runtime")
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH", "APP_VERSION"):
        environment.pop(key, None)
    for name in ENTRIES:
        executable = output / name / name
        result = subprocess.run([str(executable), "--runtime-info"], check=True,
                                capture_output=True, text=True, timeout=30,
                                cwd=output, env=environment)
        info = json.loads(result.stdout)
        if (not info.get("frozen") or info.get("implementation") != "CPython"
                or not info.get("python", "").startswith("3.14.")
                or info.get("app_version") != version):
            raise ValueError("incorrect frozen runtime: " + name)
    for name in ("LICENSE", "PYTHON-LICENSE.txt", "THIRD-PARTY-LICENSES"):
        if not (output / name).exists():
            raise ValueError("runtime notices missing: " + name)
    return document


def build(output, version):
    check_environment()
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("output must be absent or empty; refusing to replace existing files")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="speedtester-linux-freeze-") as temporary:
        stage = Path(temporary)
        app = stage / "app"
        shutil.copytree(ROOT / "app", app,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        subprocess.run([sys.executable, str(ROOT / "scripts/stamp_version.py"), str(app), version],
                       check=True)
        environment = os.environ.copy()
        environment.update(MPLBACKEND="Agg", MPLCONFIGDIR=str(stage / "mpl"))
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        for name, entry in ENTRIES.items():
            command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                       "--onedir", "--name", name, "--paths", str(app),
                       "--distpath", str(output), "--workpath", str(stage / "work" / name),
                       "--specpath", str(stage), "--exclude-module", "tkinter"]
            if name != "SpeedTesterLauncher":
                command.extend(("--collect-all", "tzdata"))
            if name == "SpeedTesterAPI":
                command.extend(("--add-data", str(app / "dashboard") + ":dashboard"))
            subprocess.run([*command, str(app / entry)], check=True, cwd=stage,
                           env=environment)
    name, libc_version = platform.libc_ver()
    components = copy_notices(output)
    document = {"format": "speedtester-linux-runtime-v1", "python": platform.python_version(),
                "app_version": version, "architecture": platform.machine(),
                "libc": {"name": name, "version": libc_version},
                "scope": "build-environment inventory; not a resolved runtime SBOM",
                "components": components}
    (output / "runtime-components.json").write_text(json.dumps(document, indent=2) + "\n")
    verify_runtime(output, version)
    print("linux-frozen-runtime-ok: " + str(output))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"(?a)\d+\.\d+\.\d+", args.version):
        parser.error("semantic package version required")
    if args.verify_only:
        verify_runtime(args.output, args.version)
    else:
        build(args.output, args.version)


if __name__ == "__main__":
    main()
