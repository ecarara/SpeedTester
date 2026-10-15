# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Minimal, authenticated OS metadata; no hostname, user, serial or raw uname."""
import platform,re,time
from uuid import uuid4
from .models import SystemEnvironment,EnvironmentReport
from .crypto import b64,public_bytes,digest,sign
from .client import ProtocolError


def collect_environment():
    system={"Linux":"linux","Windows":"windows","Darwin":"macos","FreeBSD":"freebsd"}.get(platform.system(),"other")
    machine=platform.machine().lower()
    architecture={"x86_64":"amd64","amd64":"amd64","aarch64":"arm64","arm64":"arm64","i386":"x86","i686":"x86","armv7l":"arm","armv6l":"arm"}.get(machine,"other")
    distribution=version=None
    if system=="linux":
        try:release=platform.freedesktop_os_release()
        except OSError:release={}
        candidate=release.get("ID","")
        if re.fullmatch(r"[a-z0-9._-]{1,64}",candidate):distribution=candidate
        candidate=release.get("VERSION_ID","")
        if re.fullmatch(r"[A-Za-z0-9._+-]{1,40}",candidate):version=candidate
    return SystemEnvironment(system=system,distribution=distribution,version=version,architecture=architecture)


def sync_environment(credentials,measurement_key):
    if not credentials.bundle:raise ProtocolError("pairing_required")
    status,_,discovery=credentials.transport("GET","/.well-known/speedtester-server",{},None)
    if (status!=200 or not isinstance(discovery,dict) or discovery.get("protocol_version")!="1"
        or discovery.get("origin")!=credentials.origin or discovery.get("signing_key")!=b64(public_bytes(credentials.server_key))):
        raise ProtocolError("server_configuration_invalid")
    if "client-environment-v1" not in discovery.get("capabilities",[]):return False
    environment=collect_environment();checksum=digest(environment.model_dump())
    scope=credentials.scope+":environment"
    if credentials.queue.state(scope+":sent")==checksum:return False
    pending=credentials.queue.state(scope+":pending")
    if not pending:
        report=EnvironmentReport(environment_id=str(uuid4()),client_id=credentials.bundle.client_id,reported_at=int(time.time()),environment=environment)
        pending={"report":report.model_dump(),"checksum":checksum}
        credentials.queue.state(scope+":pending",pending)
    envelope=sign(pending["report"],measurement_key,"client-environment-v1")
    credentials.client().environment(envelope)
    credentials.queue.put_batch([],scope,state_updates={scope+":sent":pending["checksum"],scope+":pending":None})
    return True
