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
import os
import re
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
    revision=os.environ.get("SOURCE_REVISION","")
    if not re.fullmatch("[0-9a-f]{40}",revision):
        result=subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,cwd=ROOT)
        revision=result.stdout.strip() if result.returncode==0 else "source"
    sys.path.insert(0,str(ROOT/"app"))
    from speedtester_protocol.version import CLIENT_VERSION
    launcher.write_text("from speedtester_protocol.version import set_build_revision\nset_build_revision("+repr(revision)+")\nfrom speedtester_protocol.desktop_entry import main\nraise SystemExit(main())\n")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--collect-all", "tzdata", "--name", "SpeedTesterClient", "--paths", str(ROOT / "app"),
        "--distpath", str(output / "raw"), "--workpath", str(work / "cache"), "--specpath", str(work)]
    if platform.system()=="Linux":
        data=Path("/usr/share/X11/locale")
        if not data.is_dir():raise RuntimeError("Xlib locale data required for Linux package")
        command.extend(("--add-data",str(data)+":x11/locale"))
        modules=[Path("/usr/lib/X11/locale"),*Path("/usr/lib").glob("*/X11/locale")]
        for directory in modules:
            for library in directory.rglob("*.so*") if directory.is_dir() else ():
                if library.is_file():
                    destination="x11/modules/"+library.parent.relative_to(directory).as_posix()
                    command.extend(("--add-binary",str(library)+":"+destination))
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
    if system=="Linux":
        notice=Path("/usr/share/doc/libx11-6/copyright")
        if notice.is_file():
            directory=bundle/"THIRD-PARTY-LICENSES/libX11"
            directory.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(notice,directory/"copyright")
    (bundle/"build-info.json").write_text(json.dumps({"version":CLIENT_VERSION,"revision":revision,"experimental":True},indent=2)+"\n")
    (bundle / "PREVIEW.txt").write_text(
        "EXPERIMENTAL DEVELOPER PREVIEW — not a certified production installer.\n"
        "CI exercises native service maintenance on disposable VMs; interactive elevation/reboot certification and iPerf3 distribution remain pending.\n"
        "Code signing/notarization, MSI/PKG/DEB/RPM integration and native uninstall registration are pending.\n"
        "Installation and pairing do not run measurements. The schedule starts disabled.\n"
        "The measurement tool is not bundled in this preview; do not enable it on a production workstation.\n")
    manifest(bundle)
    executable = bundle / ("Contents/MacOS/SpeedTesterClient" if system == "Darwin" else "SpeedTesterClient.exe" if system == "Windows" else "SpeedTesterClient")
    if smoke:
        with __import__("tempfile").TemporaryDirectory() as temporary:
            environment=os.environ.copy()
            if system=="Linux":
                environment.update(SPEEDTESTER_INPUT_SMOKE="1",XMODIFIERS="@im=none")
            subprocess.run([str(executable), "--ui-smoke"], check=True, timeout=120, cwd=temporary,env=environment)
            if system == "Linux":
                environment.update(SPEEDTESTER_INPUT_SMOKE="fallback", XMODIFIERS="@im=cararalab-ci-unavailable")
                subprocess.run([str(executable), "--ui-smoke"], check=True, timeout=120, cwd=temporary, env=environment)
    releases = output / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    name = "SpeedTesterClient-" + CLIENT_VERSION + "-" + system.lower() + "-" + platform.machine().lower()
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
