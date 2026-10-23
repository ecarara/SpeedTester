# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Private local files and process locks on POSIX and native Windows."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat


def reject_links(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError("symlinked_state_directory")
        if os.name == "nt" and item.exists():
            if item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise ValueError("reparse_state_directory")
    return path


def windows_identity():
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()


def windows_acl(path, *, principal=None, apply=False, directory=False, read_only=False):
    import ntsecuritycon as rights
    import win32con
    import win32security as security
    principal = principal or windows_identity()
    allowed = [principal, security.CreateWellKnownSid(security.WinLocalSystemSid),
               security.CreateWellKnownSid(security.WinBuiltinAdministratorsSid)]
    descriptor = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT, security.OWNER_SECURITY_INFORMATION)
    owner = descriptor.GetSecurityDescriptorOwner()
    if owner not in allowed:
        import ctypes
        if apply and owner == windows_identity() and ctypes.windll.shell32.IsUserAnAdmin():
            # A service's files are owned by Administrators, never another
            # interactive user who could silently rewrite their DACL later.
            security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
                security.OWNER_SECURITY_INFORMATION, allowed[-1], None, None, None)
        else:
            raise ValueError("state_owner_mismatch")
    if apply:
        acl = security.ACL()
        inherit = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE if directory else 0
        for sid in allowed:
            access = rights.FILE_GENERIC_READ | rights.FILE_GENERIC_EXECUTE if read_only and sid == principal else rights.FILE_ALL_ACCESS
            acl.AddAccessAllowedAceEx(security.ACL_REVISION_DS, inherit, access, sid)
        security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
            security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, acl, None)
    descriptor = security.GetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT, security.DACL_SECURITY_INFORMATION)
    acl = descriptor.GetSecurityDescriptorDacl()
    if acl is None or acl.GetAceCount() == 0:
        raise ValueError("insecure_state_acl")
    current_allowed = False
    for index in range(acl.GetAceCount()):
        ace = acl.GetAce(index)
        if ace[0][0] != security.ACCESS_ALLOWED_ACE_TYPE or ace[-1] not in allowed:
            raise ValueError("insecure_state_acl")
        if ace[-1] == principal and ace[1] & rights.FILE_GENERIC_READ:
            current_allowed = True
    if not current_allowed:
        raise ValueError("state_owner_mismatch")


def private_directory(path):
    path = reject_links(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "nt":
        windows_acl(path, apply=True, directory=True)
    else:
        if path.stat().st_uid != os.getuid():
            raise ValueError("state_owner_mismatch")
        path.chmod(0o700)
    return path


def check_private_file(path, metadata):
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("insecure_storage_key")
    if os.name == "nt":
        windows_acl(path)
    elif metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("insecure_storage_key")


def private_open(path, flags, mode=0o600):
    path = reject_links(path)
    descriptor = os.open(path, flags | getattr(os, "O_NOFOLLOW", 0), mode)
    try:
        if os.name == "nt":
            # Parent DACL is already private; explicitly protect new files too.
            windows_acl(path, apply=bool(flags & os.O_CREAT))
        check_private_file(path, os.fstat(descriptor))
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def process_lock(path):
    descriptor = private_open(path, os.O_CREAT | os.O_RDWR)
    with os.fdopen(descriptor, "r+b", buffering=0) as stream:
        if os.name == "nt":
            import msvcrt
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"\0")
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise BlockingIOError("client_already_running") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
