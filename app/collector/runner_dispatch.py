# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Select one of the supported measurement runners."""
from __future__ import annotations

from typing import Optional
from dataclasses import dataclass

from collector.iperf3_runner import run_iperf3
from collector.ookla_runner import run_ookla
from collector.speedtest_runner import SpeedTestResult, run_speedtest


RUNNER_NAMES = ("fast", "ookla", "iperf3")


@dataclass(frozen=True)
class Iperf3Target:
    """Optional destination and geographic override for the iPerf3 runner."""
    server: Optional[str] = None
    port: int = 5201
    location: Optional[dict] = None


def run_named_runner(
    name: str,
    *,
    duration_seconds: int,
    server_ids: Optional[list[int]],
    max_bytes: int,
    bandwidth_contracted_mbps: Optional[float],
    isp_lookup_enabled: bool,
    isp_lookup_timeout_seconds: float,
    ookla_binary: str = "speedtest",
    iperf3_target: Optional[Iperf3Target] = None,
    iperf3_duration_seconds: int = 10,
    iperf3_parallel_streams: int = 5,
    measurement_timeout_seconds: float = 60.0,
) -> SpeedTestResult:
    """Run one named speed-test implementation.

    Args:
        name: One of ``fast``, ``ookla`` or ``iperf3``.
        duration_seconds: Compatibility duration passed to supported runners.
        server_ids: Optional Ookla server selection.
        max_bytes: Per-stream safety ceiling used by fast.com.
        bandwidth_contracted_mbps: Contract value copied into the result.
        isp_lookup_enabled: Whether best-effort ISP lookup is allowed.
        isp_lookup_timeout_seconds: Timeout for the ISP lookup.
        ookla_binary: Path to the official Ookla executable.
        iperf3_target: Optional host, port and confirmed location.
        iperf3_duration_seconds: Duration of each iPerf3 direction.
        iperf3_parallel_streams: Number of parallel TCP streams.
        measurement_timeout_seconds: Total iPerf3 wall-clock budget.

    Returns:
        A normalized :class:`SpeedTestResult`.

    Raises:
        ValueError: If ``name`` is not a supported runner.
        RuntimeError: If the selected runner cannot complete.
    """
    normalized = name.strip().lower()
    common = {
        "duration_seconds": duration_seconds,
        "share": False,
        "server_ids": server_ids,
        "max_bytes": max_bytes,
        "bandwidth_contracted_mbps": bandwidth_contracted_mbps,
        "isp_lookup_enabled": isp_lookup_enabled,
        "isp_lookup_timeout_seconds": isp_lookup_timeout_seconds,
    }
    if normalized == "fast":
        return run_speedtest(**common)
    if normalized == "ookla":
        return run_ookla(**common, binary=ookla_binary)
    if normalized == "iperf3":
        target = iperf3_target or Iperf3Target()
        return run_iperf3(
            duration_seconds=iperf3_duration_seconds,
            share=False,
            server_ids=server_ids,
            max_bytes=max_bytes,
            bandwidth_contracted_mbps=bandwidth_contracted_mbps,
            isp_lookup_enabled=isp_lookup_enabled,
            isp_lookup_timeout_seconds=isp_lookup_timeout_seconds,
            server=target.server,
            port=target.port,
            parallel_streams=iperf3_parallel_streams,
            timeout_seconds=measurement_timeout_seconds,
            location=target.location,
        )
    raise ValueError(f"runner inválido: {name!r}; use {', '.join(RUNNER_NAMES)}")
