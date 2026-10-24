# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Runner for an operator-provided or public iperf3 server."""
from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from collector.network_metrics import measure_ping
from collector.network_identity import resolve_network_identity
from collector.speedtest_runner import SpeedTestResult, _detect_interface
from collector.target_selection import rank_targets, TargetSelectionError, CATALOG_REVISION
from shared.native_tools import iperf_binary


@dataclass(frozen=True)
class IperfRunMetrics:
    speed_mbps: float
    retransmits: Optional[int]
    transfer_bytes: Optional[int] = None


class Iperf3Timeout(RuntimeError):
    """Raised when one complete iPerf3 measurement exceeds its wall-clock budget."""


class Iperf3TargetUnavailable(RuntimeError):
    """Connection refused or server busy in either measurement direction."""


MAX_AUTOMATIC_TARGETS = 3


def _target_evidence(target, outcome, detail=None):
    return {"server_name": f"iperf3:{target.host}:{target.port}",
            "target_selection": target.mode, "target_distance_km": target.distance_km,
            "server_location": f"{target.city}, {target.country_code}" if target.city else None,
            "target_catalog_revision": CATALOG_REVISION if target.mode != "manual" else None,
            "outcome": outcome, "detail": detail}


def _measure_on_available_target(targets, execute, deadline):
    """Complete both directions on one of at most three geographic targets.

    Refusal/busy in either direction discards the entire partial pair. The next
    destination starts with a fresh upload, never retaining the old throughput,
    transfer bytes or retransmits. The original wall-clock deadline is shared.
    Timeouts and other errors retain their type for connectivity diagnostics.
    """
    if not targets:
        raise TargetSelectionError("Nenhum destino de medição disponível no catálogo.")
    attempts = []
    for target in targets[:MAX_AUTOMATIC_TARGETS]:
        remaining = _target_timeout(deadline, attempts)
        outcome = "error"
        try:
            upload = execute(target, False, remaining)
            outcome = "download_error"
            download = execute(target, True, _target_timeout(deadline, attempts))
        except RuntimeError as exc:
            attempts.append(_target_evidence(target, outcome, str(exc)[:400]))
            exc.target_attempts = attempts
            if not isinstance(exc, Iperf3TargetUnavailable) or target.mode == "manual":
                raise
            print(f"[iperf3] unavailable target {target.host}:{target.port} "
                  f"phase={'download' if outcome == 'download_error' else 'upload'}; "
                  "discarding partial measurement", flush=True)
            last_error = exc
        else:
            attempts.append(_target_evidence(target, "selected"))
            return target, upload, download, attempts
    raise last_error


def _target_timeout(deadline, attempts):
    try:
        return _remaining_timeout(deadline)
    except Iperf3Timeout as exc:
        exc.target_attempts = attempts
        raise


def _failure_detail(completed):
    """Extract iPerf's error, not its machine/system-info JSON envelope."""
    detail = (completed.stderr or completed.stdout or "sem detalhes").strip()
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return detail[-240:]
    message = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(message, str):
        return message[:240]
    return detail[-240:]


def _initial_identity(server, location, enabled, timeout, deadline):
    if (server and server.strip()) or location:
        return {}
    if not enabled:
        raise TargetSelectionError("A localização automática está desativada. Confirme sua localização ou informe um servidor opcional.")
    return resolve_network_identity(min(timeout, _remaining_timeout(deadline)))


def _enrich_identity(identity, enabled, timeout, deadline):
    remaining = max(deadline - time.monotonic(), 0.0)
    if enabled and not identity and remaining > 0.1:
        return resolve_network_identity(min(timeout, remaining))
    return identity


def run_iperf3(
    duration_seconds: int = 10,
    share: bool = False,
    server_ids: Optional[list[int]] = None,
    max_bytes: int = 10_000_000,
    bandwidth_contracted_mbps: Optional[float] = None,
    isp_lookup_enabled: bool = True,
    isp_lookup_timeout_seconds: float = 5.0,
    server: Optional[str] = None,
    port: int = 5201,
    parallel_streams: int = 5,
    binary: str = "iperf3",
    timeout_seconds: float = 60.0,
    location: Optional[dict] = None,
) -> SpeedTestResult:
    """Use one live geographic target, or exactly the user's manual target."""
    del share, server_ids, max_bytes
    if duration_seconds < 1 or parallel_streams < 1:
        raise ValueError("iperf3 duration and parallel streams must be positive")
    if timeout_seconds <= 0:
        raise ValueError("iperf3 timeout must be positive")

    started = time.monotonic()
    deadline = started + timeout_seconds
    if binary == "iperf3":
        binary = iperf_binary()
    identity = _initial_identity(server, location, isp_lookup_enabled, isp_lookup_timeout_seconds, deadline)
    targets = rank_targets(server, port, location=location or identity)

    def execute(target, reverse, remaining):
        return _run_once_metrics(binary, target.host, target.port, duration_seconds,
                                 parallel_streams, reverse=reverse, timeout_seconds=remaining)

    target, upload_metrics, download_metrics, target_attempts = _measure_on_available_target(targets, execute, deadline)
    server, port = target.host, target.port
    remaining = _target_timeout(deadline, target_attempts)
    if remaining <= 5.0:
        error = Iperf3Timeout(
            f"iperf3 excedeu o timeout total de {timeout_seconds:.0f} segundos"
        )
        error.target_attempts = target_attempts
        raise error
    # measure_ping has a minimum subprocess timeout of five seconds. Reduce
    # the per-packet budget so the quality probe also stays inside the total
    # measurement deadline.
    ping_timeout = min(2.0, max((remaining - 3.0) / 5.0, 0.1))
    network = measure_ping(server, timeout_seconds=ping_timeout)
    retransmits = _sum_optional(
        upload_metrics.retransmits, download_metrics.retransmits
    )
    # Optional enrichment shares the total measurement deadline.
    identity = _enrich_identity(identity, isp_lookup_enabled, isp_lookup_timeout_seconds, deadline)
    interface = _detect_interface(timeout_seconds=min(5.0, _target_timeout(deadline, target_attempts)))
    _target_timeout(deadline, target_attempts)
    return SpeedTestResult(
        download_mbps=download_metrics.speed_mbps,
        upload_mbps=upload_metrics.speed_mbps,
        ping_ms=network.ping_ms,
        jitter_ms=network.jitter_ms,
        latency_min_ms=network.latency_min_ms,
        latency_max_ms=network.latency_max_ms,
        packet_loss_pct=network.packet_loss_pct,
        tcp_retransmits=retransmits,
        server_id=None,
        server_name=f"iperf3:{server}:{port}",
        server_location=f"{target.city}, {target.country_code}" if target.city else None,
        target_selection=target.mode,
        target_distance_km=target.distance_km,
        target_catalog_revision=CATALOG_REVISION if target.mode != "manual" else None,
        target_attempts=target_attempts,
        country=identity.get("country"),
        interface=interface,
        bandwidth_contracted_mbps=bandwidth_contracted_mbps,
        isp=identity.get("isp") if isp_lookup_enabled else None,
        duration_sec=time.monotonic() - started,
        transfer_bytes=(upload_metrics.transfer_bytes + download_metrics.transfer_bytes
                        if upload_metrics.transfer_bytes is not None and download_metrics.transfer_bytes is not None else None),
        city=identity.get("city"),
        public_ip=identity.get("public_ip"),
        country_code=identity.get("country_code"),
        isp_organization=identity.get("isp_organization"),
        asn=identity.get("asn"),
        isp_source=identity.get("isp_source"),
        isp_confidence=identity.get("isp_confidence"),
        isp_observed_at=identity.get("isp_observed_at"),
    )


def _run_once(
    binary: str,
    server: str,
    port: int,
    duration_seconds: int,
    parallel_streams: int,
    reverse: bool,
) -> float:
    return _run_once_metrics(
        binary, server, port, duration_seconds, parallel_streams, reverse
    ).speed_mbps


def _run_once_metrics(
    binary: str,
    server: str,
    port: int,
    duration_seconds: int,
    parallel_streams: int,
    reverse: bool,
    timeout_seconds: Optional[float] = None,
) -> IperfRunMetrics:
    command = [
        binary,
        "--client",
        server,
        "--port",
        str(port),
        "--time",
        str(duration_seconds),
        "--parallel",
        str(parallel_streams),
        "--omit",
        "2",
        "--json",
    ]
    if reverse:
        command.append("--reverse")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=(
                timeout_seconds
                if timeout_seconds is not None
                else duration_seconds * 2 + 30
            ),
            start_new_session=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"iperf3 não encontrado: {binary}") from exc
    except subprocess.TimeoutExpired as exc:
        if timeout_seconds is not None:
            raise Iperf3Timeout(
                f"iperf3 excedeu o timeout total de {timeout_seconds:.0f} segundos"
            ) from exc
        raise RuntimeError("iperf3 excedeu o timeout") from exc
    if completed.returncode != 0:
        detail = _failure_detail(completed)
        message = f"iperf3 {server}:{port} falhou ({completed.returncode}): {detail}"
        if any(marker in detail.lower() for marker in ("connection refused", "server is busy")):
            raise Iperf3TargetUnavailable(message)
        raise RuntimeError(message)

    try:
        payload = json.loads(completed.stdout)
        end = payload["end"]
        summary = end["sum_received"] if reverse else end["sum_sent"]
        retransmits = summary.get("retransmits")
        if retransmits is None:
            retransmits = end.get("sum_sent", {}).get("retransmits")
        return IperfRunMetrics(
            speed_mbps=float(summary["bits_per_second"]) / 1_000_000,
            retransmits=int(retransmits) if retransmits is not None else None,
            transfer_bytes=int(summary["bytes"]) if summary.get("bytes") is not None else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"iperf3 não retornou JSON reconhecível: {completed.stdout[-400:]}") from exc


def _sum_optional(*values: Optional[int]) -> Optional[int]:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _remaining_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise Iperf3Timeout("iperf3 excedeu o timeout total da medição")
    return remaining
