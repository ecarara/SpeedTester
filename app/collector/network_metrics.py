# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Small, dependency-free network quality probes shared by all runners."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PingMetrics:
    """Summary of an ICMP probe batch."""

    ping_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    latency_min_ms: Optional[float] = None
    latency_max_ms: Optional[float] = None
    packet_loss_pct: Optional[float] = None


def measure_ping(
    host: str,
    *,
    attempts: int = 5,
    timeout_seconds: float = 2.0,
) -> PingMetrics:
    """Measure ICMP latency, jitter and packet loss to ``host``.

    ``ping_ms`` is the median RTT. ``jitter_ms`` is the mean absolute change
    between consecutive RTTs in the order received. If ICMP is unavailable or
    filtered, all values remain ``None`` instead of turning a speed test into
    a failure.
    """
    if not host or attempts < 1:
        return PingMetrics()
    command = [
        "ping",
        "-n",
        "-c",
        str(attempts),
        "-W",
        str(max(float(timeout_seconds), 0.1)),
        host,
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=max(attempts * timeout_seconds + 3.0, 5.0),
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return PingMetrics()

    output = f"{completed.stdout}\n{completed.stderr}"
    # Support both dot and comma decimal separators emitted by ping variants.
    raw_rtts = re.findall(r"time[=<]([0-9]+(?:[.,][0-9]+)?)\s*ms", output)
    rtts = [float(value.replace(",", ".")) for value in raw_rtts]

    loss_match = re.search(r"([0-9]+(?:[.,][0-9]+)?)%\s*packet loss", output)
    packet_loss = (
        float(loss_match.group(1).replace(",", ".")) if loss_match else None
    )
    if packet_loss is None and not rtts and completed.returncode != 0:
        packet_loss = 100.0
    if not rtts:
        return PingMetrics(packet_loss_pct=packet_loss)

    ordered = sorted(rtts)
    median = ordered[len(ordered) // 2]
    diffs = [abs(current - previous) for previous, current in zip(rtts, rtts[1:])]
    return PingMetrics(
        ping_ms=median,
        jitter_ms=sum(diffs) / len(diffs) if diffs else 0.0,
        latency_min_ms=min(rtts),
        latency_max_ms=max(rtts),
        packet_loss_pct=packet_loss if packet_loss is not None else 0.0,
    )
