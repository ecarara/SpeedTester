# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Private installation state; user services need no machine-wide credentials."""
import os,secrets,stat
from pathlib import Path
from .queue import EncryptedQueue


def protected_queue(directory):
    directory=Path(directory).absolute()
    if any(path.is_symlink() for path in (directory,*directory.parents)):
        raise ValueError("symlinked_state_directory")
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    if directory.stat().st_uid!=os.getuid():raise ValueError("state_owner_mismatch")
    os.chmod(directory,0o700)
    keyfile=directory/"storage.key"
    flags=os.O_RDWR|os.O_NOFOLLOW
    try:
        fd=os.open(keyfile,flags|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
    except FileExistsError:
        pass
    fd=os.open(keyfile,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,"rb") as stream:
        metadata=os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=os.getuid() or stat.S_IMODE(metadata.st_mode)&0o077:
            raise ValueError("insecure_storage_key")
        key=stream.read(33)
    if len(key)!=32:raise ValueError("invalid_storage_key")
    return EncryptedQueue(directory,key)


def systemd_unit(executable,directory):
    def quote(value):
        value=str(Path(value).absolute())
        if any(c in value for c in '\n\r\x00'):raise ValueError("invalid_service_path")
        return '"'+value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')+'"'
    command=quote(executable)+" run --state "+quote(directory)
    return f'''# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
[Unit]
Description=SpeedTester community client
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart={command}
Restart=on-failure
RestartSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={quote(directory)}
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
[Install]
WantedBy=default.target
'''
