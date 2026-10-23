# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Accurate network speed measurement built on top of fast.com.

The previous wrapper relied on the official Ookla ``speedtest`` binary
(``$SPEEDTEST_BIN``). In practice that path picked a single nearest
speedtest.net server and was heavily affected by that server's load and
geography, which produced results far below the real throughput of the link
(inside this appliance we observe hundreds of Mbps, whereas the Ookla path
reported single digits to low tens).

fast.com instead downloads from up to five CDN edge connections in parallel,
so its measurement tracks the true capacity of the path much better.  This
module reuses that exact download methodology (five parallel connections,
7-30s warm-up until the rate stabilises) and mirrors it for the upload
direction, which fast.com does not measure.  A lightweight RTT measurement is
added for ping/jitter on top.

The public surface (:class:`SpeedTestResult` and :func:`run_speedtest`) keeps
the same field names and argument list the collector depends on, so switching
to this runner is a drop-in replacement.

Every result is reported in **Mbps (Megabits per second)**.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import ssl
import time
import urllib.parse
from dataclasses import dataclass
from typing import Optional

import aiohttp

from collector.network_metrics import measure_ping
from collector.network_identity import resolve_network_identity

# fast.com constants (kept local so we can stop the test early if the operator
# requests a shorter run or hit a wall-clock budget).
MIN_DURATION = 7.0
STABILITY_DELTA = 2.0
MIN_STABLE_MEASUREMENTS = 6
# fast.com streams 64 KiB chunks; the connection is "done" when the fifth one
# finishes, so we never need more than five concurrent downloads.
CHUNK_SIZE = 64 * 1024
CONCURRENT_CONNECTIONS = 5


@dataclass
class SpeedTestResult:
    """Normalized result shared by every measurement runner.

    Speeds and latency values are expressed in Mbps and milliseconds. Optional
    fields remain ``None`` when a runner or the network does not provide them;
    callers must not replace missing metrics with zero.
    """

    download_mbps: float
    upload_mbps: float
    ping_ms: Optional[float]
    jitter_ms: Optional[float]
    latency_min_ms: Optional[float]
    latency_max_ms: Optional[float]
    packet_loss_pct: Optional[float]
    tcp_retransmits: Optional[int]
    server_id: Optional[int]
    server_name: Optional[str]
    server_location: Optional[str]
    country: Optional[str]
    interface: Optional[str]
    bandwidth_contracted_mbps: Optional[float]
    isp: Optional[str]
    duration_sec: float
    transfer_bytes: Optional[int] = None
    city: Optional[str] = None
    public_ip: Optional[str] = None
    country_code: Optional[str] = None
    isp_organization: Optional[str] = None
    asn: Optional[str] = None
    isp_source: Optional[str] = None
    isp_confidence: Optional[str] = None
    isp_observed_at: Optional[str] = None
    target_selection: Optional[str] = None
    target_distance_km: Optional[float] = None
    target_catalog_revision: Optional[str] = None
    target_attempts: Optional[list[dict]] = None


def run_speedtest(
    duration_seconds: int = 30,
    share: bool = False,
    server_ids: Optional[list[int]] = None,
    max_bytes: int = 10_000_000,
    bandwidth_contracted_mbps: Optional[float] = None,
    isp_lookup_enabled: bool = True,
    isp_lookup_timeout_seconds: float = 5.0,
) -> SpeedTestResult:
    """Execute one round-trip speed measurement against fast.com.

    Args:
        duration_seconds: retained for API compatibility. The test self-terminates
            when its rate stabilises (7-30s); this only bounds the worst case.
        share: retained for API compatibility; result sharing is not enabled.
        server_ids: retained for API compatibility; fast.com routes around server
            selection, so the preferred IDs are ignored.
        max_bytes: retained for API compatibility; used only as a hard per-stream
            ceiling if the host is very constrained.
        bandwidth_contracted_mbps: operator-configured contract, stored alongside
            the sample (the ``BANDWIDTH_CONTRACTED`` env var sets it per device).
        isp_lookup_enabled: retained for API compatibility; controls the best
            effort ISP lookup used when fast.com does not report one.
        isp_lookup_timeout_seconds: timeout for the best-effort ISP lookup.

    Returns:
        A :class:`SpeedTestResult` with speeds in Mbps (Megabits per second).
    """
    t0 = time.monotonic()

    loop = asyncio.new_event_loop()
    try:
        # Bound the whole run so a hung network can never wedge the collector.
        result = loop.run_until_complete(
            _run_async(
                duration_seconds=duration_seconds,
                max_bytes=max_bytes,
                isp_lookup_enabled=isp_lookup_enabled,
                isp_lookup_timeout_seconds=isp_lookup_timeout_seconds,
            )
        )
    finally:
        loop.close()

    # Best-effort interface detection, matching the previous behaviour.
    try:
        interface = _detect_interface()
    except Exception:  # pragma: no cover - best effort only
        interface = None

    duration_sec = time.monotonic() - t0
    return SpeedTestResult(
        download_mbps=result["download_mbps"],
        upload_mbps=result["upload_mbps"],
        ping_ms=result["ping_ms"],
        jitter_ms=result["jitter_ms"],
        latency_min_ms=result["latency_min_ms"],
        latency_max_ms=result["latency_max_ms"],
        packet_loss_pct=result["packet_loss_pct"],
        tcp_retransmits=result["tcp_retransmits"],
        server_id=result["server_id"],
        server_name=result["server_name"],
        server_location=None,
        country=result["country"],
        interface=interface,
        isp=result["isp"],
        bandwidth_contracted_mbps=bandwidth_contracted_mbps,
        duration_sec=duration_sec,
        city=result.get("city"),
        public_ip=result.get("public_ip"),
        country_code=result.get("country_code"),
        isp_organization=result.get("isp_organization"),
        asn=result.get("asn"),
        isp_source=result.get("isp_source"),
        isp_confidence=result.get("isp_confidence"),
        isp_observed_at=result.get("isp_observed_at"),
    )


async def _run_async(
    duration_seconds: int = 30,
    max_bytes: int = 10_000_000,
    isp_lookup_enabled: bool = True,
    isp_lookup_timeout_seconds: float = 5.0,
) -> dict:
    """Drive the download, upload and ping measurements and return a dict."""
    deadline = time.monotonic() + max(30, duration_seconds + 30)
    timeout = aiohttp.ClientTimeout(total=deadline - time.monotonic())

    async with aiohttp.ClientSession(timeout=timeout) as session:
        token = await _get_token(session)
        urls = await _get_urls(session, token)

        # --- download --------------------------------------------------------
        download_mbps = await _measure_speed(
            session, urls, "download", duration_seconds, max_bytes, deadline
        )

        # --- upload ----------------------------------------------------------
        upload_mbps = await _measure_upload(
            session, urls, duration_seconds, max_bytes, deadline
        )

    # --- ping --------------------------------------------------------------
    network = await asyncio.to_thread(measure_ping, "fast.com")
    if network.ping_ms is None:
        # ICMP is commonly filtered on public endpoints; keep the existing
        # TCP/HTTPS fallback so fast.com still reports a useful latency.
        ping_ms, jitter_ms = await _measure_ping()
        latency_min_ms = ping_ms
        latency_max_ms = ping_ms
        packet_loss_pct = None
    else:
        ping_ms = network.ping_ms
        jitter_ms = network.jitter_ms
        latency_min_ms = network.latency_min_ms
        latency_max_ms = network.latency_max_ms
        packet_loss_pct = network.packet_loss_pct

    # --- ISP ---------------------------------------------------------------
    isp = None
    identity = {}
    if isp_lookup_enabled:
        isp = await _resolve_isp(isp_lookup_timeout_seconds)
        # The legacy helper is retained for compatibility with integrations
        # and tests.  The structured lookup adds city/country/ASN metadata.
        identity = await asyncio.to_thread(
            resolve_network_identity,
            isp_lookup_timeout_seconds,
            isp_hint=isp,
        )

    return {
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
        "ping_ms": ping_ms,
        "jitter_ms": jitter_ms,
        "latency_min_ms": latency_min_ms,
        "latency_max_ms": latency_max_ms,
        "packet_loss_pct": packet_loss_pct,
        "tcp_retransmits": None,
        "server_id": None,
        "server_name": "fast.com",
        "country": identity.get("country"),
        "isp": identity.get("isp") or isp,
        "city": identity.get("city"),
        "public_ip": identity.get("public_ip"),
        "country_code": identity.get("country_code"),
        "isp_organization": identity.get("isp_organization"),
        "asn": identity.get("asn"),
        "isp_source": identity.get("isp_source"),
        "isp_confidence": identity.get("isp_confidence"),
        "isp_observed_at": identity.get("isp_observed_at"),
    }


# ---------------------------------------------------------------------------
# fast.com download / upload methodology
# ---------------------------------------------------------------------------
async def _get_token(session: "aiohttp.ClientSession") -> str:
    async with session.get("https://fast.com/") as resp:
        text = await resp.text()
    match = re.search(r'<script src="(.*?)">', text)
    if not match:
        raise RuntimeError("fast.com page did not expose a measurement script")
    script = match.group(1)
    async with session.get(f"https://fast.com{script}") as resp:
        script_text = await resp.text()
    token = re.search(r'token:"(.*?)"', script_text)
    if not token:
        raise RuntimeError("fast.com script did not expose a token")
    return token.group(1)


async def _get_urls(
    session: "aiohttp.ClientSession", token: str
) -> list[str]:
    params = urllib.parse.urlencode(
        {"https": "true", "token": token, "urlCount": CONCURRENT_CONNECTIONS}
    )
    async with session.get(
        f"https://api.fast.com/netflix/speedtest?{params}"
    ) as resp:
        data = await resp.json()
    return [entry["url"] for entry in data]


async def _measure_speed(
    session: "aiohttp.ClientSession",
    urls: list[str],
    direction: str,
    duration_seconds: int,
    max_bytes: int,
    deadline: float,
) -> float:
    """Download over the CDN URLs until the rate stabilises.

    The connections are warmed up and streamed until the moving rate stops
    drifting. Upload uses :func:`_measure_upload`, because it must account for
    completed HTTP POST requests rather than local payload generation.
    """
    if not urls:
        raise RuntimeError("fast.com returned no measurement URLs")
    if direction != "download":
        raise ValueError("_measure_speed only supports download")

    # Per-phase wall-clock bound: each direction runs for ``duration_seconds``
    # (bounded by MIN_DURATION) rather than the shared run-wide ``deadline``,
    # which lets the caller request short runs without being throttled by the
    # 30s floor used to guard a hung network.
    phase_deadline = time.monotonic() + max(float(duration_seconds), MIN_DURATION)

    # Warm up all download connections first.
    connections = [
        (url, conn)
        for url, conn in zip(
            urls,
            await _gather_open(_open_connection, urls, direction, session, max_bytes),
        )
    ]

    start = time.monotonic()
    moving_total = 0
    moving_start = time.monotonic()
    measurements: list[float] = []
    deltas: list[float] = []

    def _current_speed() -> float:
        elapsed = max(time.monotonic() - moving_start, 1e-6)
        return (moving_total / elapsed) * 8.0 / 1e6  # bytes/s -> Mbps

    def _sample() -> None:
        nonlocal moving_total
        speed = _current_speed()
        measurements.append(speed)
        if len(measurements) > 10:
            measurements.pop(0)
        if len(measurements) > 1:
            prev = measurements[-2]
            if prev > 0:
                deltas.append(abs(speed - prev) / prev * 100.0)
                if len(deltas) > 10:
                    deltas.pop(0)

    def _stabilized() -> bool:
        return (
            len(deltas) >= 2
            and (time.monotonic() - start) > min(float(duration_seconds), MIN_DURATION)
            and max(deltas) < STABILITY_DELTA
        )

    # Pump every stream concurrently, feeding a shared moving window. Each
    # stream pumps until the wall-clock deadline (enforced by the session
    # timeout) or its payload is exhausted, so liveness is tracked by the
    # session timeout rather than per-connection completion.
    try:
        while time.monotonic() < phase_deadline:
            moved_this_round = [0]
            await asyncio.gather(
                *[
                    _pump_one(session, conn, direction, max_bytes, moved_this_round, phase_deadline)
                    for _url, conn in connections
                ]
            )
            moving_total += moved_this_round[0]
            _sample()
            if _stabilized():
                break
            # fast.com may finish a finite CDN response before the phase ends.
            # Replace that response so the next round still measures network
            # traffic instead of repeatedly polling an EOF StreamReader.
            refreshed = []
            for url, conn in connections:
                if conn._exhausted:
                    await _release(conn)
                    conn = await _open_connection(url, direction, session, max_bytes)
                refreshed.append((url, conn))
            connections = refreshed
            await asyncio.sleep(0.2)
    finally:
        # Ensure all streams are released even on early stop.
        await asyncio.gather(
            *[_release(conn) for _url, conn in connections],
            return_exceptions=True,
        )

    return _current_speed()


async def _open_connection(url, direction, session, max_bytes):
    """Open one measurement connection and wrap it in a small tracker.

    Returns an object exposing ``._resp`` (the response) so the outer loop can
    release it cleanly.
    """
    request = session.get(url)
    response = await request
    return _ConnTracker(response)


async def _release(conn):
    if conn._done:
        return
    try:
        await conn._resp.release()
    except Exception:
        pass
    finally:
        conn._done = True


async def _pump_one(session, conn, direction, max_bytes, moved_sink, deadline):
    moved = await _pump(conn, direction, max_bytes, deadline)
    moved_sink[0] += moved


# --- the real per-connection pump -----------------------------------------
# ---------------------------------------------------------------------------
async def _pump(
    conn,
    direction: str,
    max_bytes: int,
    deadline: float,
) -> int:
    """Read one download connection until its stream ends or the deadline.

    The download path drains the stream in 64 KiB chunks (mirroring fast.com).
    Upload is measured separately by completed POST requests.
    """
    moved = 0
    if conn._exhausted:
        return 0
    try:
        if direction == "download":
            resp = conn._resp
            async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
                moved += len(chunk)
                if time.monotonic() >= deadline:
                    break
            else:
                # An edge can finish its response before the measurement
                # phase. Do not iterate the same EOF stream again: aiohttp
                # warns and repeatedly polls when StreamReader is already at
                # EOF.
                conn._exhausted = True
    except Exception:
        # A single dead edge should not sink the whole measurement; the other
        # streams keep running and we keep the largest good reading.
        conn._exhausted = True
    return moved


def _upload_payload() -> bytes:
    """Random-ish bytes so the upload is not trivially compressible."""
    return os.urandom(1024)


async def _measure_upload(
    session,
    urls: list[str],
    duration_seconds: int,
    max_bytes: int,
    deadline: float,
) -> float:
    """Measure upload using completed HTTP POST requests.

    The previous implementation incremented a counter while preparing an
    async-generator body. That measured local payload generation, not bytes
    that crossed the network. Each worker now sends finite requests with an
    explicit Content-Length and counts the payload only after the response is
    received. Requests are repeated until the phase deadline and run in
    parallel across the fast.com edges.
    """
    if not urls:
        raise RuntimeError("fast.com returned no measurement URLs")

    phase_seconds = max(float(duration_seconds), MIN_DURATION)
    phase_deadline = min(time.monotonic() + phase_seconds, deadline)
    payload_size = max(64 * 1024, min(max_bytes, 16 * 1024 * 1024))
    payload = os.urandom(payload_size)
    phase_start = time.monotonic()
    totals = await asyncio.gather(
        *[
            _upload_worker(session, url, payload, phase_deadline)
            for url in urls
        ]
    )
    elapsed = max(time.monotonic() - phase_start, 1e-6)
    total_bytes = sum(totals)
    if total_bytes <= 0:
        raise RuntimeError("fast.com upload transferred no bytes")
    return (total_bytes / elapsed) * 8.0 / 1e6


async def _upload_worker(session, url: str, payload: bytes, deadline: float) -> int:
    """Send finite, measured POST requests over one CDN edge."""
    total = 0
    headers = {
        "Content-Length": str(len(payload)),
        "Content-Type": "application/octet-stream",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    while time.monotonic() < deadline:
        try:
            async with session.post(url, data=payload, headers=headers) as resp:
                await resp.read()
            total += len(payload)
        except Exception:
            break
    return total


async def _gather_open(open_fn, urls: list[str], direction: str, session, max_bytes) -> list:
    tasks = [open_fn(url, direction, session, max_bytes) for url in urls]
    return await asyncio.gather(*tasks)


class _ConnTracker:
    """Small holder around a single measurement response.

    The pump loop keeps the connection open for the whole measurement and
    releases it exactly once in the outer ``finally``; this object tracks that
    single-release state so we never double-release.
    """

    __slots__ = ("_resp", "_done", "_exhausted")

    def __init__(self, response) -> None:
        self._resp = response
        self._done = False
        self._exhausted = False


async def _measure_ping(
    timeout: float = 2.0, attempts: int = 10
) -> tuple[Optional[float], Optional[float]]:
    """Round-trip time to fast.com using raw sockets.

    fast.com does not expose latency, so we measure it ourselves. We open a
    TCP connection and, once established, send a single HTTP request and time
    the first byte. Repeated a handful of times so we can report a stable ping
    (median) and jitter (mean absolute deviation between consecutive RTTs).
    """
    rtts: list[float] = []
    host = "fast.com"
    for _ in range(attempts):
        try:
            rtts.append(await _one_rtt(host, timeout))
        except Exception:
            continue
    if not rtts:
        return None, None
    sorted_rtts = sorted(rtts)
    ping = sorted_rtts[len(sorted_rtts) // 2]  # median is robust to outliers
    diffs = [
        abs(sorted_rtts[i] - sorted_rtts[i - 1]) for i in range(1, len(sorted_rtts))
    ]
    jitter = sum(diffs) / len(diffs) if diffs else 0.0
    return ping, jitter


async def _one_rtt(host: str, timeout: float) -> float:
    """Time TLS connection and the first response byte within a total budget."""
    writer = None
    start = time.perf_counter()
    try:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        async with asyncio.timeout(timeout):
            reader, writer = await asyncio.open_connection(
                host, 443, ssl=context, server_hostname=host)
            writer.write(b"GET / HTTP/1.1\r\nHost: fast.com\r\nConnection: close\r\n\r\n")
            await writer.drain()
            if not await reader.read(1):
                raise OSError('HTTPS probe closed before responding')
            return (time.perf_counter()-start)*1000.0
    finally:
        if writer is not None:
            writer.close()
            try:
                async with asyncio.timeout(min(timeout, 1.0)):
                    await writer.wait_closed()
            except OSError:
                pass


def _eligible_interface(line: str) -> Optional[str]:
    """Keep the existing active-link and virtual/link-local exclusions."""
    parts = line.split()
    if len(parts) < 2:
        return None
    iface = parts[0]
    if iface == "lo" or iface.startswith(("veth", "br-")):
        return None
    if "LOWER_UP" not in line or "169.254" in line:
        return None
    return iface


def _preferred_interface(output: str) -> Optional[str]:
    """First eligible wired link wins; otherwise keep the first wireless."""
    wireless = None
    for line in output.splitlines():
        iface = _eligible_interface(line)
        if iface is None:
            continue
        if iface.startswith(("eth", "enp", "ene", "ens", "enx", "ecm", "enq", "enO")):
            return iface
        if wireless is None and iface.startswith(("wl", "wlan", "wlp")):
            wireless = iface
    return wireless


def _detect_interface(timeout_seconds: float = 5.0) -> Optional[str]:
    """Best-effort detection of the primary wired (RJ45) interface name.

    Prefers wired (eth*, enp*, ecm*, ...) over wireless (wl*, wlan, wlp) so
    measurements reflect the primary path. When no wired interface is up,
    falls back to the first wireless interface with a link.
    """
    try:
        import subprocess

        out = subprocess.run(
            ["ip", "-br", "addr"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        ).stdout
        return _preferred_interface(out)
    except Exception:  # pragma: no cover - best effort
        return None


async def _resolve_isp(timeout_seconds: float = 5.0) -> Optional[str]:
    """Best-effort ISP identification for the client's network.

    fast.com returns client metadata (``x-fast-isp-header``) on the speedtest
    API response, which we prefer. We fall back to a public IP lookup service
    (ipwho.is) only when the header is absent.
    """
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://fast.com", timeout=aiohttp.ClientTimeout(total=timeout_seconds)
            ) as resp:
                isp = resp.headers.get("x-fast-isp-header")
            if isp:
                return str(isp)
    except Exception:
        pass

    try:
        import urllib.request

        with urllib.request.urlopen(
            "https://ipwho.is/?fields=success,connection.isp,connection.org", timeout=timeout_seconds
        ) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("success"):
            return None
        connection = data.get("connection", {})
        return connection.get("isp") or connection.get("org")
    except Exception:
        return None  # pragma: no cover - network dependent, best effort
