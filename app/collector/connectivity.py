# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Best-effort local and external connectivity probes."""
from __future__ import annotations

import socket
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConnectivitySnapshot:
    """Evidence captured before or after a speed test."""

    gateway: str | None
    gateway_reachable: bool
    external_reachable: bool
    evidence: dict[str, Any]


def probe_connectivity(timeout_seconds: float = 2.0) -> ConnectivitySnapshot:
    """Probe the default gateway and independent external TCP endpoints.

    This is deliberately evidence collection, not proof of an operator fault.
    The collector only uses the resulting categories when the gateway is
    reachable and all independent external probes fail.
    """
    gateway, interface = _default_route()
    gateway_ports = _probe_host(gateway, (53, 80, 443), timeout_seconds)
    external_results = {
        host: _probe_dns_and_tcp(host, timeout_seconds)
        for host in ("fast.com", "www.gstatic.com", "example.com")
    }
    external_reachable = any(result["reachable"] for result in external_results.values())
    return ConnectivitySnapshot(
        gateway=gateway,
        gateway_reachable=bool(gateway_ports),
        external_reachable=external_reachable,
        evidence={
            "interface": interface,
            "gateway": gateway,
            "gateway_ports": gateway_ports,
            "external": external_results,
        },
    )


def _default_route() -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        parts = result.stdout.split()
        gateway = parts[parts.index("via") + 1] if "via" in parts else None
        interface = parts[parts.index("dev") + 1] if "dev" in parts else None
        return gateway, interface
    except Exception:
        return None, None


def _probe_host(host: str | None, ports: tuple[int, ...], timeout: float) -> list[int]:
    if not host:
        return []
    reachable: list[int] = []
    for port in ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                reachable.append(port)
        except OSError:
            continue
    return reachable


def _probe_dns_and_tcp(host: str, timeout: float) -> dict[str, Any]:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"dns": False, "reachable": False, "error": str(exc)[:200]}
    for family, socktype, proto, _canonname, sockaddr in addresses:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.settimeout(timeout)
                sock.connect(sockaddr)
            return {"dns": True, "reachable": True}
        except OSError:
            continue
    return {"dns": True, "reachable": False}
