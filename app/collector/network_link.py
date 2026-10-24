# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Read-only, bounded identification of the local link used by a measurement.

Prefer native runner interface/source-address evidence, then a literal-IP route,
then the default route. Never rank active adapters by their name. This describes
the local link, not the ISP's last-mile technology; Wi-Fi to a phone is Wi-Fi.
No DNS queries, probes, privileges, SSIDs or MAC-address persistence are needed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time


@dataclass(frozen=True)
class NetworkLink:
    interface: str | None = None
    connection_type: str = "unknown"
    source: str = "unavailable"
    scope: str = "unknown"
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def evidence(self) -> dict:
        """Only normalized context, never raw native output or local addresses."""
        return {"interface": self.interface, "type": self.connection_type,
                "source": self.source, "scope": self.scope, "observed_at": self.observed_at}

    def result_fields(self) -> dict:
        return {"interface": self.interface, "connection_type": self.connection_type,
                "connection_source": self.source, "connection_scope": self.scope,
                "connection_observed_at": self.observed_at, "connection_evidence": self.evidence()}


def literal_ip(value) -> str | None:
    try:
        address = ipaddress.ip_address(str(value).split("%", 1)[0])
        return None if address.is_unspecified else str(address)
    except ValueError:
        return None


def _interface(value) -> str | None:
    if not isinstance(value, str) or not value or value in {".", ".."} or len(value) > 128 or value.startswith("-"):
        return None
    if any(ord(c) < 32 or c in "/\\" for c in value):
        return None
    return value


class _Probe:
    def __init__(self, timeout):
        self.deadline = time.monotonic() + max(0, timeout)

    def run(self, command, input=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return ""
        try:
            completed = subprocess.run(command, input=input, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=remaining, check=False,
                env={**os.environ, "LC_ALL": "C"})
            return completed.stdout if completed.returncode == 0 and len(completed.stdout) <= 262144 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""


def _rows(output):
    try:
        value = json.loads(output)
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def _text(path):
    try:
        with path.open(encoding="utf-8", errors="replace") as source:
            return source.read(4096).strip()
    except OSError:
        return ""


def _linux_interface(probe, local_ip, remote_ip, hint):
    if hint:
        return hint, "runner_interface"
    if local_ip:
        matches = {row.get("ifname") for row in _rows(probe.run(["ip", "-j", "address", "show"]))
                   if isinstance(row, dict) and any(literal_ip(a.get("local")) == local_ip
                       for a in row.get("addr_info", []) if isinstance(a, dict))}
        return (next(iter(matches)), "runner_address") if len(matches) == 1 else (None, "runner_address")
    if remote_ip:
        rows = _rows(probe.run(["ip", "-j", "route", "get", remote_ip]))
        return (rows[0].get("dev") if rows and isinstance(rows[0], dict) else None), "destination_route"
    interfaces = set()
    for family in ("-4", "-6"):
        rows = _rows(probe.run(["ip", "-j", family, "route", "show", "default"]))
        if rows:
            routes = [row for row in rows if isinstance(row, dict) and row.get("dev")]
            metric = min((row.get("metric", 0) for row in routes), default=None)
            interfaces.update(row["dev"] for row in routes if row.get("metric", 0) == metric)
    return (next(iter(interfaces)) if len(interfaces) == 1 else None), "default_route"


def _linux_type(interface, probe, root):
    device = root / interface
    if (device / "wireless").is_dir() or (device / "phy80211").exists():
        return "wifi", "linux-sysfs"
    hardware_type = _text(device / "type")
    if hardware_type == "772":
        return "loopback", "linux-sysfs"
    if hardware_type == "512":
        return "point_to_point", "linux-sysfs"
    if "DEVTYPE=wwan" in _text(device / "uevent"):
        return "cellular", "linux-sysfs"
    rows = _rows(probe.run(["ip", "-j", "-d", "link", "show", "dev", interface]))
    row = rows[0] if rows and isinstance(rows[0], dict) else {}
    kind = (row.get("linkinfo") or {}).get("info_kind")
    if kind in {"tun", "wireguard", "gre", "gretap", "ipip", "sit", "vti", "ip6tnl", "vxlan"}:
        return "tunnel", "linux-rtnetlink"
    if kind in {"veth", "bridge", "bond", "vlan", "macvlan", "ipvlan", "dummy", "team"}:
        return "virtual", "linux-rtnetlink"
    if hardware_type == "1" and (device / "device").exists():
        return "ethernet", "linux-sysfs"
    return "unknown", "linux-unclassified"


def _linux(probe, local_ip, remote_ip, hint, root):
    interface, scope = _linux_interface(probe, local_ip, remote_ip, hint)
    interface = _interface(interface)
    if not interface:
        return NetworkLink(scope=scope)
    kind, source = _linux_type(interface, probe, root)
    return NetworkLink(interface, kind, source, scope)


def _mac_address_interface(output, local_ip):
    interface, matches = None, set()
    for line in output.splitlines():
        if line and not line[0].isspace():
            interface = line.split(":", 1)[0]
        parts = line.split()
        if len(parts) > 1 and parts[0] in ("inet", "inet6") and literal_ip(parts[1]) == local_ip:
            matches.add(interface)
    return next(iter(matches)) if len(matches) == 1 else None


def _mac_route_interface(output):
    match = re.search(r"^\s*interface:\s*(\S+)", output, re.M)
    return match.group(1) if match else None


def _mac_interface(probe, local_ip, remote_ip, hint):
    if hint:
        return hint, "runner_interface"
    if local_ip:
        return _mac_address_interface(probe.run(["/sbin/ifconfig", "-a"]), local_ip), "runner_address"
    if not remote_ip:
        interfaces = set()
        for family in ("-inet", "-inet6"):
            output = probe.run(["/sbin/route", "-n", "get", family, "default"])
            name = _mac_route_interface(output)
            if name:
                interfaces.add(name)
        return (next(iter(interfaces)) if len(interfaces) == 1 else None), "default_route"
    scope = "destination_route" if remote_ip else "default_route"
    args = ["/sbin/route", "-n", "get"]
    if remote_ip and ":" in remote_ip:
        args.append("-inet6")
    output = probe.run(args + [remote_ip or "default"])
    return _mac_route_interface(output), scope


def _hardware_port_type(port):
    if port in {"wi-fi", "airport"}:
        return "wifi"
    for word, kind in (("bridge", "virtual"), ("bluetooth", "bluetooth"),
                       ("ethernet", "ethernet"), (" lan", "ethernet"), ("usb", "usb")):
        if word in port:
            return kind
    return "unknown"


def _mac_type(interface, output):
    port = ""
    for line in output.splitlines():
        if line.startswith("Hardware Port: "):
            port = line.partition(": ")[2].casefold()
        if line == "Device: " + interface:
            return _hardware_port_type(port)
    return "unknown"


def _mac(probe, local_ip, remote_ip, hint):
    name, scope = _mac_interface(probe, local_ip, remote_ip, hint)
    name = _interface(name)
    if not name:
        return NetworkLink(scope=scope)
    if name == "lo0":
        return NetworkLink(name, "loopback", "macos-kernel-interface", scope)
    # utun is Apple's kernel tunnel device, not evidence of the physical uplink.
    if re.fullmatch(r"utun\d+", name):
        return NetworkLink(name, "tunnel", "macos-kernel-interface", scope)
    kind = _mac_type(name, probe.run(["/usr/sbin/networksetup", "-listallhardwareports"]))
    return NetworkLink(name, kind, "macos-hardwareports", scope)


_WINDOWS_SCRIPT = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding=[System.Text.UTF8Encoding]::new($false)
$q=[Console]::In.ReadToEnd() | ConvertFrom-Json
$index=$null
$scope='default_route'
if ($q.hint) {
  $index=(Get-NetAdapter -IncludeHidden | Where-Object Name -eq $q.hint | Select-Object -First 1).ifIndex
  $scope='runner_interface'
} elseif ($q.local_ip) {
  $indices=@(Get-NetIPAddress -IPAddress $q.local_ip | Select-Object -ExpandProperty InterfaceIndex -Unique)
  if ($indices.Count -eq 1) { $index=$indices[0] }
  $scope='runner_address'
} elseif ($q.remote_ip) {
  $index=(Find-NetRoute -RemoteIPAddress $q.remote_ip | Select-Object -First 1).InterfaceIndex
  $scope='destination_route'
} else {
  $routes=@(Get-NetRoute | Where-Object { $_.DestinationPrefix -in @('0.0.0.0/0','::/0') } |
    ForEach-Object {
      $ip=Get-NetIPInterface -InterfaceIndex $_.InterfaceIndex -AddressFamily $_.AddressFamily
      if ($ip.ConnectionState -eq 'Connected') {
        [pscustomobject]@{Index=$_.InterfaceIndex;Family=$_.AddressFamily;Metric=($_.RouteMetric+$ip.InterfaceMetric)}
      }
    })
  $indices=@($routes | Group-Object Family | ForEach-Object {
    $best=($_.Group | Measure-Object Metric -Minimum).Minimum
    $_.Group | Where-Object Metric -eq $best | Select-Object -ExpandProperty Index
  } | Select-Object -Unique)
  if ($indices.Count -eq 1) { $index=$indices[0] }
}
if ($null -eq $index) { @{scope=$scope} | ConvertTo-Json -Compress; exit }
$adapter=Get-NetAdapter -IncludeHidden | Where-Object ifIndex -eq $index | Select-Object -First 1
@{name=$adapter.Name;physical_medium=[int]$adapter.NdisPhysicalMedium;interface_type=[int]$adapter.InterfaceType;
  hardware=$adapter.HardwareInterface;virtual=$adapter.Virtual;scope=$scope} | ConvertTo-Json -Compress
'''


def _windows_type(row):
    medium, interface_type = row.get("physical_medium"), row.get("interface_type")
    if interface_type == 24:
        return "loopback"
    if interface_type == 131:
        return "tunnel"
    if row.get("virtual") is True or row.get("hardware") is False:
        return "virtual"
    if medium in (1, 9):
        return "wifi"
    if medium == 8:
        return "cellular"
    if medium == 10:
        return "bluetooth"
    if row.get("hardware") is True and medium == 14:
        return "ethernet"
    return "unknown"


def _windows(probe, local_ip, remote_ip, hint):
    output = probe.run(["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_SCRIPT],
                       input=json.dumps({"local_ip": local_ip, "remote_ip": remote_ip, "hint": hint}))
    try:
        row = json.loads(output)
    except (ValueError, TypeError):
        return NetworkLink()
    if not isinstance(row, dict):
        return NetworkLink()
    name = _interface(row.get("name"))
    return NetworkLink(name, _windows_type(row) if name else "unknown", "windows-netadapter", row.get("scope", "unknown"))


def detect_link(*, local_ip=None, remote_ip=None, interface_hint=None, timeout_seconds=5.0) -> NetworkLink:
    """Inspect local OS metadata only; unavailable/ambiguous evidence is unknown.

    A default-route observation is explicitly marked as such, not claimed as a
    socket-bound observation. Every subprocess shares one monotonic deadline.
    """
    probe = _Probe(timeout_seconds)
    local_ip, remote_ip, hint = literal_ip(local_ip), literal_ip(remote_ip), _interface(interface_hint)
    try:
        system = platform.system()
        if system == "Linux":
            return _linux(probe, local_ip, remote_ip, hint, Path("/sys/class/net"))
        if system == "Darwin":
            return _mac(probe, local_ip, remote_ip, hint)
        if system == "Windows":
            return _windows(probe, local_ip, remote_ip, hint)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return NetworkLink()
