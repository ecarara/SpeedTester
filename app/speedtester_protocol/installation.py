# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Private installation state; user services need no machine-wide credentials."""
import os,secrets
from pathlib import Path
from .queue import EncryptedQueue
from .local_security import private_directory,private_open


def protected_queue(directory):
    directory=private_directory(directory)
    keyfile=directory/"storage.key"
    if (directory/"index.sqlite").exists() and not keyfile.exists():
        raise ValueError("storage_key_missing")
    try:
        fd=private_open(keyfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
        with os.fdopen(fd,"wb") as stream:
            stream.write(secrets.token_bytes(32));stream.flush();os.fsync(stream.fileno())
    except FileExistsError:
        pass
    fd=private_open(keyfile,os.O_RDONLY)
    with os.fdopen(fd,"rb") as stream:
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
