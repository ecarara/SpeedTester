# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Unprivileged GUI controller and explicit native elevation boundary."""
import json
import os
from pathlib import Path
import platform
import secrets
import shlex
import subprocess
import sys
import tempfile
from .local_control import ControlClient
from .local_security import private_directory, private_open

DEFAULT_SERVER = "https://speedtester.cararalab.com.br"


def control_directory():
    system = platform.system()
    if system == "Windows":
        from win32com.shell import shell, shellcon
        return Path(shell.SHGetFolderPath(0, shellcon.CSIDL_LOCAL_APPDATA, None, 0)) / "CararaLab/SpeedTesterClient"
    if system == "Darwin":
        return Path.home() / "Library/Application Support/CararaLab/SpeedTesterClientControl"
    return Path.home() / ".config/cararalab/speedtester-client"


class DesktopController:
    preview = False

    def __init__(self, directory=None):
        self.directory = private_directory(directory or control_directory())
        self.control = self.directory / "control.json"
        try:
            descriptor = private_open(self.control, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "w") as stream:
                json.dump({"format": 1, "key": secrets.token_hex(32)}, stream)
        with os.fdopen(private_open(self.control, os.O_RDONLY), "r") as stream:
            stored = json.load(stream)
        if set(stored) != {"format", "key"} or stored["format"] != 1 or len(stored["key"]) != 64:
            raise ValueError("invalid_control_configuration")
        self.key = bytes.fromhex(stored["key"])
        self.client = ControlClient(self.key)

    def call(self, operation, arguments=None):
        return self.client.call(operation, arguments)

    def native(self, operation, purge=False):
        if not getattr(sys, "frozen", False):
            raise ValueError("packaged_installer_required")
        request = {"operation": operation, "control_key": self.key.hex(), "purge": purge}
        # Paths only on the command line; never a token or control secret.
        with tempfile.TemporaryDirectory(prefix="maintenance-", dir=self.directory) as temporary:
            path = Path(temporary) / "request.json"
            with os.fdopen(private_open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY), "w") as stream:
                json.dump(request, stream)
            command = [sys.executable, "--native-helper", str(path)]
            system = platform.system()
            if system == "Windows":
                import win32api
                import win32con
                import win32event
                import win32process
                from win32com.shell import shell, shellcon
                process = shell.ShellExecuteEx(fMask=shellcon.SEE_MASK_NOCLOSEPROCESS, lpVerb="runas",
                    lpFile=sys.executable, lpParameters=subprocess.list2cmdline(command[1:]), nShow=win32con.SW_HIDE)
                handle = process["hProcess"]
                try:
                    if win32event.WaitForSingleObject(handle, 600000) != win32event.WAIT_OBJECT_0:
                        raise TimeoutError("native_operation_incomplete")
                    code = win32process.GetExitCodeProcess(handle)
                finally:
                    win32api.CloseHandle(handle)
            elif system == "Darwin":
                script = "do shell script " + json.dumps(shlex.join(command)) + " with administrator privileges"
                code = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, timeout=600).returncode
            else:
                code = subprocess.run(["/usr/bin/pkexec", *command], capture_output=True, timeout=600).returncode
            if code not in (0, 10):
                raise RuntimeError("native_operation_failed")
        if operation == "uninstall" and purge:
            self.control.unlink(missing_ok=True)
        return {"ok": True, "reboot_required": code == 10, "data_preserved": not purge}


class PreviewController:
    """Explicitly labelled UI fixture: no network, elevation, services or runner."""
    preview = True

    def __init__(self):
        self.state = {"ok": True, "service": "running", "code": "ready", "configured": False,
            "paired": False, "contribute": False, "measurements_enabled": False, "pending": 0,
            "quarantined": 0, "database_bytes": 0, "last_tick": 0}

    def call(self, operation, arguments=None):
        if operation == "configure":
            self.state.update(configured=True, contribute=arguments["contribute"])
        elif operation == "pair":
            self.state["pairing"] = {"user_code": "ABCDE-F2345", "verification_uri": DEFAULT_SERVER + "/pair",
                "fingerprint": "0" * 64, "expires_at": 2000000000}
        elif operation == "pause":
            self.state["measurements_enabled"] = False
        return self.state.copy()

    def native(self, operation, purge=False):
        return {"ok": True, "reboot_required": False, "data_preserved": not purge}
