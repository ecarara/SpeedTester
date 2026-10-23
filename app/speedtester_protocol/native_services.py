# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Fixed native service layouts and privilege-separated lifecycle operations.

Only a frozen application may invoke the privileged helper. It accepts no shell
commands, installation directories, service names, users or executable paths.
"""
from dataclasses import dataclass
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
from .local_security import reject_links, windows_acl
from .desktop_links import system_environment

SYSTEMCTL = "/usr/bin/systemctl"
LAUNCHCTL = "/bin/launchctl"
SYSTEM_DOMAIN = "system/"
EMPTY_HOME = "/var/empty"
DSCL = "/usr/bin/dscl"
INDEX_FILENAME = "index.sqlite"
STORAGE_KEY_FILENAME = "storage.key"

SERVICE = "CararaLabSpeedTesterClient"
LABEL = "com.cararalab.speedtester.client"
MARKER = "cararalab-speedtester-desktop-v1"
BOOTSTRAP = "service.json"
INVALID_NATIVE_REQUEST = "invalid_native_request"


@dataclass(frozen=True)
class Layout:
    system: str
    runtime: Path
    state: Path
    executable: Path
    definition: Path | None
    user: str


def native_layout(system=None):
    system = system or platform.system()
    if system == "Linux":
        runtime = Path("/opt/cararalab/speedtester-client")
        return Layout(system, runtime, Path("/var/lib/cararalab-speedtester-client"),
            runtime / "SpeedTesterClient", Path("/etc/systemd/system/cararalab-speedtester-client.service"), "speedtester-client")
    if system == "Darwin":
        runtime = Path("/Applications/CararaLab SpeedTester Client.app")
        return Layout(system, runtime, Path("/Library/Application Support/CararaLab/SpeedTesterClient"),
            runtime / "Contents/MacOS/SpeedTesterClient", Path("/Library/LaunchDaemons") / (LABEL + ".plist"), "_speedtester")
    if system == "Windows":
        from win32com.shell import shell, shellcon
        runtime = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_PROGRAM_FILES, None, 0)) / "CararaLab/SpeedTesterClient"
        state = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_COMMON_APPDATA, None, 0)) / "CararaLab/SpeedTesterClient"
        return Layout(system, runtime, state, runtime / "SpeedTesterClient.exe", None, "NT SERVICE\\" + SERVICE)
    raise ValueError("unsupported_platform")


def system_service_unit(layout):
    def quote(path):
        value = str(path)
        if any(char in value for char in '\r\n\0'):
            raise ValueError("invalid_service_path")
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
    return f'''[Unit]
Description=CararaLab SpeedTester Client
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User={layout.user}
Group={layout.user}
ExecStart={quote(layout.executable)} --agent
Restart=on-failure
RestartSec=30
TimeoutStopSec=330
KillMode=control-group
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={quote(layout.state / 'queue')}
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=multi-user.target
'''


def launch_daemon(layout):
    return plistlib.dumps({"Label": LABEL, "ProgramArguments": [str(layout.executable), "--agent"],
        "UserName": layout.user, "GroupName": layout.user, "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 30,
        "ExitTimeOut": 330, "WorkingDirectory": "/", "Umask": 0o077})


def checked(command, *, allowed=(0,)):
    result = subprocess.run(command, capture_output=True, text=True, timeout=360, env=system_environment())
    if result.returncode not in allowed:
        raise RuntimeError("native_service_operation_failed:"+str(result.returncode))
    return result.stdout


def trusted_parent(path):
    """Create root-owned parents without inheriting a private helper umask."""
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for existing in (current, *current.parents):
        reject_links(existing)
        if os.name != "nt":
            metadata = existing.stat()
            admin_group = platform.system() == "Darwin" and metadata.st_gid == 80
            if metadata.st_uid != 0 or metadata.st_mode & 0o002 or (metadata.st_mode & 0o020 and not admin_group):
                raise ValueError("insecure_installation_parent")
    for item in reversed(missing):
        item.mkdir(mode=0o755)
        if os.name != "nt":
            os.chown(item, 0, 0)
            item.chmod(0o755)


def _stop_launchd_service():
    loaded = subprocess.run([LAUNCHCTL, "print", SYSTEM_DOMAIN + LABEL], capture_output=True, timeout=10, env=system_environment()).returncode == 0
    if loaded:
        checked([LAUNCHCTL, "bootout", SYSTEM_DOMAIN + LABEL])
        # launchd may retain the job briefly after bootout returns. Starting
        # it immediately can fail with EIO, so wait for the label to unload.
        deadline = time.monotonic() + 30
        while subprocess.run([LAUNCHCTL, "print", SYSTEM_DOMAIN + LABEL],
                capture_output=True, timeout=10, env=system_environment()).returncode == 0:
            if time.monotonic() >= deadline:
                raise RuntimeError("native_service_stop_timeout")
            time.sleep(.25)


def _stop_windows_service():
    import win32service
    import win32serviceutil
    import pywintypes
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE)[1]
    except pywintypes.error as exc:
        if exc.winerror == 1060:
            return
        raise
    if status != win32service.SERVICE_STOPPED:
        win32serviceutil.StopService(SERVICE)
        win32serviceutil.WaitForServiceStatus(SERVICE, win32service.SERVICE_STOPPED, 360)


def stop_service(layout):
    if layout.system == "Linux":
        if layout.definition.exists():
            checked([SYSTEMCTL, "stop", layout.definition.name])
            checked([SYSTEMCTL, "is-active", layout.definition.name], allowed=(3,))
    elif layout.system == "Darwin":
        _stop_launchd_service()
    else:
        _stop_windows_service()


def register_service(layout):
    if layout.system == "Linux":
        layout.definition.write_text(system_service_unit(layout))
        layout.definition.chmod(0o644)
        checked([SYSTEMCTL, "daemon-reload"])
        checked([SYSTEMCTL, "enable", layout.definition.name])
    elif layout.system == "Darwin":
        layout.definition.write_bytes(launch_daemon(layout))
        layout.definition.chmod(0o644)
    else:
        import win32service
        import win32serviceutil
        import pywintypes
        options = {"startType": win32service.SERVICE_AUTO_START, "userName": layout.user,
            "exeName": str(layout.executable), "exeArgs": "--windows-service",
            "description": "CararaLab SpeedTester Client"}
        try:
            win32serviceutil.QueryServiceStatus(SERVICE)
        except pywintypes.error as exc:
            if exc.winerror != 1060:
                raise
            win32serviceutil.InstallService("speedtester_protocol.windows_service.SpeedTesterWindowsService",
                SERVICE, "CararaLab SpeedTester Client", **options)
        else:
            win32serviceutil.ChangeServiceConfig("speedtester_protocol.windows_service.SpeedTesterWindowsService", SERVICE, **options)


def start_service(layout):
    if layout.system == "Linux":
        checked([SYSTEMCTL, "start", layout.definition.name])
    elif layout.system == "Darwin":
        deadline = time.monotonic() + 15
        while True:
            result = subprocess.run([LAUNCHCTL, "bootstrap", "system", str(layout.definition)],
                capture_output=True, timeout=30, env=system_environment())
            if result.returncode == 0:
                break
            if result.returncode != 5 or time.monotonic() >= deadline:
                raise RuntimeError("native_service_bootstrap_failed:"+str(result.returncode))
            time.sleep(.5)
    else:
        import win32serviceutil
        win32serviceutil.StartService(SERVICE)


def wait_for_service(key):
    from .local_control import ControlClient
    deadline = time.monotonic() + 30
    while True:
        try:
            status = ControlClient(bytes.fromhex(key), timeout=1).call("status")
            if status.get("ok") and status.get("service") == "running":
                return
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("native_service_health_failed")
        time.sleep(.25)


def remove_service(layout):
    stop_service(layout)
    if layout.system == "Linux":
        if layout.definition.exists():
            checked([SYSTEMCTL, "disable", layout.definition.name])
            layout.definition.unlink()
            checked([SYSTEMCTL, "daemon-reload"])
    elif layout.system == "Darwin":
        layout.definition.unlink(missing_ok=True)
    else:
        import win32serviceutil
        import pywintypes
        try:
            win32serviceutil.RemoveService(SERVICE)
        except pywintypes.error as exc:
            if exc.winerror != 1060:
                raise


def _create_posix_identity(layout):
    if layout.system == "Linux":
        checked(["/usr/sbin/useradd", "--system", "--user-group", "--home-dir", EMPTY_HOME,
            "--shell", "/usr/sbin/nologin", layout.user])
    else:
        users = checked([DSCL, ".", "-list", "/Users", "UniqueID"])
        groups = checked([DSCL, ".", "-list", "/Groups", "PrimaryGroupID"])
        occupied = {int(row.split()[-1]) for row in (users + "\n" + groups).splitlines() if row.split()}
        identifier = next((number for number in range(499, 199, -1) if number not in occupied), None)
        if identifier is None:
            raise ValueError("service_identity_unavailable")
        for record, values in (("/Groups/" + layout.user, {"PrimaryGroupID": str(identifier)}),
                ("/Users/" + layout.user, {"UniqueID": str(identifier), "PrimaryGroupID": str(identifier),
                    "UserShell": "/usr/bin/false", "NFSHomeDirectory": EMPTY_HOME, "IsHidden": "1", "Password": "*"})):
            checked([DSCL, ".", "-create", record])
            for key, value in values.items():
                checked([DSCL, ".", "-create", record, key, value])


def provision_identity(layout):
    if layout.system == "Windows":
        # Register the virtual-account service before resolving its SID.
        register_service(layout)
        import win32security
        return win32security.LookupAccountName(None, layout.user)[0]
    import pwd
    try:
        identity = pwd.getpwnam(layout.user)
    except KeyError:
        _create_posix_identity(layout)
        identity = pwd.getpwnam(layout.user)
    if identity.pw_uid == 0 or identity.pw_dir != EMPTY_HOME or identity.pw_shell not in ("/usr/sbin/nologin", "/usr/bin/false"):
        raise ValueError("unexpected_service_identity")
    return identity


def protect_layout(layout, identity):
    layout.state.mkdir(mode=0o750, parents=True, exist_ok=True)
    queue = layout.state / "queue"
    queue.mkdir(mode=0o700, exist_ok=True)
    if layout.system == "Windows":
        windows_acl(layout.state, principal=identity, apply=True, directory=True, read_only=True)
        windows_acl(queue, principal=identity, apply=True, directory=True)
    else:
        os.chown(layout.state, 0, identity.pw_gid)
        layout.state.chmod(0o750)
        os.chown(queue, identity.pw_uid, identity.pw_gid)
        queue.chmod(0o700)


def bundle_root():
    if not getattr(sys, "frozen", False):
        raise ValueError("packaged_installer_required")
    executable = Path(sys.executable).resolve()
    if platform.system() == "Darwin":
        return next(parent for parent in executable.parents if parent.suffix == ".app")
    return executable.parent


def verify_bundle(root):
    manifest_path = root / "bundle-manifest.json"
    if manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("invalid_bundle_manifest")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != MARKER or not isinstance(manifest.get("files"), dict):
        raise ValueError("invalid_bundle_manifest")
    expected = manifest["files"]
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("external_bundle_link")
        if not path.is_file() or path == manifest_path:
            continue
        relative = path.relative_to(root).as_posix()
        actual.add(relative)
        with path.open("rb") as stream:
            if expected.get(relative) != hashlib.file_digest(stream, "sha256").hexdigest():
                raise ValueError("bundle_integrity_failed")
    if actual != set(expected):
        raise ValueError("bundle_integrity_failed")
    return manifest


def verify_database(directory):
    reject_links(directory)
    database, keyfile = directory / INDEX_FILENAME, directory / STORAGE_KEY_FILENAME
    if not database.exists():
        if keyfile.exists():
            raise ValueError("incomplete_local_state")
        return
    if not keyfile.exists() or database.is_symlink() or keyfile.is_symlink():
        raise ValueError("incomplete_local_state")
    key = keyfile.read_bytes()
    if len(key) != 32:
        raise ValueError("invalid_storage_key")
    from .queue import EncryptedQueue
    # Read-only inspection; no implicit schema creation, data correction or key generation.
    cipher = object.__new__(EncryptedQueue)
    cipher.key = key
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("local_database_corrupt")
        for key_name, value in connection.execute("SELECT key,value FROM state"):
            cipher.open(value, key_name)
        for identifier, value, destination, receipt in connection.execute("SELECT id,ciphertext,destination,receipt FROM entries"):
            cipher.open(value, identifier + ":" + destination)
            if receipt:
                cipher.open(receipt, identifier + ":receipt")


def backup_state(layout):
    directory = layout.state / "queue"
    verify_database(directory)
    database = directory / INDEX_FILENAME
    if not database.exists():
        return
    destination = layout.state / "backups" / str(time.time_ns())
    destination.mkdir(mode=0o700, parents=True)
    if layout.system == "Windows":
        windows_acl(destination, apply=True, directory=True)
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(destination / INDEX_FILENAME)) as target:
            source.backup(target)
    shutil.copyfile(directory / STORAGE_KEY_FILENAME, destination / STORAGE_KEY_FILENAME)
    for path in destination.iterdir():
        path.chmod(0o600)
    # Backups contain the key: they inherit the service's restricted Windows DACL.
    for old in sorted(destination.parent.iterdir())[:-2]:
        if old.is_dir() and not old.is_symlink():
            shutil.rmtree(old)


def read_request(path):
    # The helper is elevated while the request belongs to the interactive user.
    # Validate that owner's private file, rather than requiring root ownership.
    path = reject_links(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(INVALID_NATIVE_REQUEST)
        if os.name == "nt":
            import win32security
            owner = win32security.GetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION).GetSecurityDescriptorOwner()
            # Administrators can own a newly created private file even when
            # its DACL grants the individual creator access. The elevated helper
            # must validate that creator's DACL, not treat the group as creator.
            from .local_security import windows_identity
            administrators = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid)
            principal = windows_identity() if owner == administrators else owner
            windows_acl(path, principal=principal)
        elif metadata.st_mode & 0o077:
            raise ValueError("insecure_native_request")
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError(INVALID_NATIVE_REQUEST)
    request = json.loads(raw)
    if (set(request) != {"operation", "control_key", "purge"}
            or request["operation"] not in ("install", "repair", "uninstall")
            or type(request["purge"]) is not bool or not isinstance(request["control_key"], str)
            or len(request["control_key"]) != 64):
        raise ValueError(INVALID_NATIVE_REQUEST)
    key = bytes.fromhex(request["control_key"])
    if len(key) != 32:
        raise ValueError(INVALID_NATIVE_REQUEST)
    return request


def write_bootstrap(layout, key, identity):
    path = layout.state / BOOTSTRAP
    path.write_text(json.dumps({"format": MARKER, "control_key": key}))
    if layout.system == "Windows":
        windows_acl(path, principal=identity, apply=True, read_only=True)
    else:
        os.chown(path, 0, identity.pw_gid)
        path.chmod(0o640)


def remove_runtime(layout):
    if not layout.runtime.exists():
        return False
    try:
        shutil.rmtree(layout.runtime)
        return False
    except OSError:
        if layout.system != "Windows":
            raise
        import win32api
        import win32con
        # A running GUI or helper may still map the executable. Stop the service
        # now and let Windows finish removing locked files at reboot.
        for path in sorted(layout.runtime.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            win32api.MoveFileEx(str(path), None, win32con.MOVEFILE_DELAY_UNTIL_REBOOT)
        win32api.MoveFileEx(str(layout.runtime), None, win32con.MOVEFILE_DELAY_UNTIL_REBOOT)
        return True


def require_admin():
    if os.name == "nt":
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise PermissionError("administrator_required")
    elif os.geteuid() != 0:
        raise PermissionError("administrator_required")


def _prepare_maintenance_state(layout, operation):
    backup_state(layout)
    # Upgrades preserve active/paused choice, credentials and all records.
    # A repair deliberately pauses; both skip slots due during maintenance.
    database = layout.state / "queue/index.sqlite"
    if database.exists():
        from .queue import EncryptedQueue
        cipher = object.__new__(EncryptedQueue)
        cipher.key = (layout.state / "queue/storage.key").read_bytes()
        with closing(sqlite3.connect(database)) as connection:
            with connection:
                if operation == "repair":
                    connection.execute("INSERT OR REPLACE INTO state VALUES(?,?)",
                        ("desktop:measurements_enabled", cipher.seal(False, "desktop:measurements_enabled")))
                connection.execute("INSERT OR REPLACE INTO state VALUES(?,?)",
                    ("desktop:upgrade_pending", cipher.seal(True, "desktop:upgrade_pending")))


def _stage_runtime(source, staged, layout, control_key, existing):
    try:
        shutil.copytree(source, staged, symlinks=True)
        verify_bundle(staged)
    except BaseException:
        if staged.exists():
            shutil.rmtree(staged)
        if existing:
            start_service(layout)
            wait_for_service(control_key)
        raise
    if os.name != "nt":
        for path in (staged, *staged.rglob("*")):
            os.chown(path, 0, 0)
            if path.is_dir():
                path.chmod(0o755)
            elif path.stat().st_mode & 0o111:
                path.chmod(0o755)
            else:
                path.chmod(0o644)


def _activate_runtime(layout, staged, previous, control_key, existing):
    swapped = False
    try:
        if layout.runtime.exists():
            layout.runtime.rename(previous)
        staged.rename(layout.runtime)
        swapped = True
        identity = provision_identity(layout)
        protect_layout(layout, identity)
        write_bootstrap(layout, control_key, identity)
        if layout.system != "Windows":
            register_service(layout)
        start_service(layout)
        wait_for_service(control_key)
    except BaseException:
        if swapped:
            stop_service(layout)
            shutil.rmtree(layout.runtime)
        if previous.exists():
            previous.rename(layout.runtime)
            # Preserve data and leave maintenance paused; never hide the failure.
            start_service(layout)
            wait_for_service(control_key)
        elif not existing:
            remove_service(layout)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def _validate_managed_paths(layout):
    for path in (layout.runtime, layout.state, layout.definition):
        if path:
            reject_links(path)


def _installation_transaction(layout, source, request):
    _validate_managed_paths(layout)
    bootstrap = layout.state / BOOTSTRAP
    existing = json.loads(bootstrap.read_text()) if bootstrap.exists() else None
    if existing:
        if existing.get("format") != MARKER or not hmac.compare_digest(existing.get("control_key", ""), request["control_key"]):
            raise PermissionError("installation_control_mismatch")
    elif request["operation"] != "install" or layout.runtime.exists() or layout.state.exists():
        raise ValueError("managed_installation_not_found")
    staged = layout.runtime.with_name(layout.runtime.name + ".new")
    previous = layout.runtime.with_name(layout.runtime.name + ".previous")
    if request["operation"] != "uninstall":
        if source.resolve() == layout.runtime.resolve():
            raise ValueError("open_downloaded_installer_for_repair")
        if staged.exists() or previous.exists():
            raise ValueError("previous_installation_transaction_exists")
    return existing, staged, previous


def native_operation(request):
    layout = native_layout()
    require_admin()
    source = bundle_root()
    verify_bundle(source)
    trusted_parent(layout.runtime.parent)
    trusted_parent(layout.state.parent)
    existing, staged, previous = _installation_transaction(layout, source, request)
    stop_service(layout)
    if request["operation"] == "uninstall":
        remove_service(layout)
        reboot = remove_runtime(layout)
        if request["purge"]:
            shutil.rmtree(layout.state)
        return {"ok": True, "reboot_required": reboot, "data_preserved": not request["purge"], "central_revocation": "not_requested"}
    if existing:
        _prepare_maintenance_state(layout, request["operation"])
    # Install from a separate downloaded bundle. Never mutate the running GUI's
    # own directory or overwrite a runtime that Windows is still mapping.
    layout.runtime.parent.mkdir(parents=True, exist_ok=True)
    _stage_runtime(source, staged, layout, request["control_key"], existing)
    _activate_runtime(layout, staged, previous, request["control_key"], existing)
    return {"ok": True, "measurements_enabled": False, "data_preserved": bool(existing)}
