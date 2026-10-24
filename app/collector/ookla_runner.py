# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Runner for the official Ookla Speedtest CLI binary."""
from __future__ import annotations

import json
import subprocess
import time
from typing import Optional

from collector.network_metrics import measure_ping
from collector.speedtest_runner import SpeedTestResult
from collector.network_link import detect_link


def run_ookla(
    duration_seconds: int = 30,
    share: bool = False,
    server_ids: Optional[list[int]] = None,
    max_bytes: int = 10_000_000,
    bandwidth_contracted_mbps: Optional[float] = None,
    isp_lookup_enabled: bool = True,
    isp_lookup_timeout_seconds: float = 5.0,
    binary: str = "speedtest",
) -> SpeedTestResult:
    """Run Ookla's native CLI and convert its JSON result to project fields."""
    del duration_seconds, share, max_bytes, isp_lookup_enabled, isp_lookup_timeout_seconds
    command = [binary, "--accept-license", "--accept-gdpr", "--progress=no", "--format=json"]
    if server_ids:
        command.extend(["--server-id", str(server_ids[0])])

    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Ookla CLI não encontrado: {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Ookla CLI excedeu o timeout de 120 segundos") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "sem detalhes").strip()
        raise RuntimeError(f"Ookla CLI falhou ({completed.returncode}): {detail[-400:]}")

    payload = _extract_json(completed.stdout)
    server = payload.get("server") or {}
    client = payload.get("client") or {}
    interface = payload.get("interface") or {}
    ping = payload.get("ping") or {}
    download = payload.get("download") or {}
    upload = payload.get("upload") or {}
    server_host = _server_host(server.get("host"))
    network = measure_ping(server_host) if server_host else None
    native_ping = _number(ping.get("latency"))
    native_jitter = _number(ping.get("jitter"))
    ping_ms = native_ping if native_ping is not None else _metric(network, "ping_ms")
    jitter_ms = native_jitter if native_jitter is not None else _metric(network, "jitter_ms")
    link = detect_link(interface_hint=interface.get("name"), local_ip=interface.get("internalIp"), remote_ip=server.get("ip"))

    return SpeedTestResult(
        download_mbps=_bits_to_mbps(download.get("bandwidth")),
        upload_mbps=_bits_to_mbps(upload.get("bandwidth")),
        ping_ms=ping_ms,
        jitter_ms=jitter_ms,
        latency_min_ms=_first_number(
            ping.get("low"), _metric(network, "latency_min_ms"), ping_ms
        ),
        latency_max_ms=_first_number(
            ping.get("high"), _metric(network, "latency_max_ms"), ping_ms
        ),
        packet_loss_pct=_first_number(
            payload.get("packetLoss"), payload.get("packet_loss"), _metric(network, "packet_loss_pct")
        ),
        tcp_retransmits=None,
        server_id=_int(server.get("id")),
        server_name=server.get("name"),
        server_location=server.get("location"),
        country=client.get("country") or server.get("country"),
        city=client.get("city") or server.get("city"),
        country_code=client.get("countryCode") or client.get("country_code") or server.get("countryCode"),
        **link.result_fields(),
        bandwidth_contracted_mbps=bandwidth_contracted_mbps,
        isp=payload.get("isp"),
        duration_sec=time.monotonic() - started,
    )


def _extract_json(output: str) -> dict:
    """Extract a JSON object even if the CLI prefixes diagnostic lines."""
    decoder = json.JSONDecoder()
    for index, character in enumerate(output):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(output[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and ("download" in value or value.get("type") == "result"):
            return value
    raise RuntimeError(f"Ookla CLI não retornou JSON reconhecível: {output[-400:]}")


def _bits_to_mbps(value) -> float:
    if value is None:
        raise RuntimeError("Ookla CLI retornou velocidade ausente")
    return float(value) * 8.0 / 1_000_000


def _number(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(*values) -> Optional[float]:
    for value in values:
        number = _number(value)
        if number is not None:
            return number
    return None


def _metric(metrics, name: str) -> Optional[float]:
    return getattr(metrics, name) if metrics is not None else None


def _server_host(value) -> Optional[str]:
    """Normalize Ookla's host[:port] field for an ICMP probe."""
    if not value:
        return None
    host = str(value).strip()
    if host.startswith("[") and "]" in host:
        return host[1 : host.index("]")]
    if host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit():
        return host.rsplit(":", 1)[0]
    return host


def _int(value) -> Optional[int]:
    return int(value) if value is not None else None
