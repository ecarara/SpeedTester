# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Best-effort public-network identity lookup.

The speed test itself remains authoritative for throughput.  This module only
enriches a completed result with metadata exposed by the public IP provider:
IP, operator, organisation/ASN, country and city.  Lookup failures are
deliberately non-fatal so a metadata provider cannot turn a valid measurement
into a failed measurement.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from copy import deepcopy
from typing import Optional


DEFAULT_CACHE_SECONDS = 6 * 60 * 60
_cache_lock = threading.Lock()
_cached_identity: Optional[dict] = None
_cached_at = 0.0


def resolve_network_identity(
    timeout_seconds: float = 5.0,
    *,
    cache_seconds: float = DEFAULT_CACHE_SECONDS,
    force: bool = False,
    isp_hint: Optional[str] = None,
) -> dict:
    """Return normalized network metadata, or an empty identity on failure.

    The cache is process-local and intentionally short-lived.  Persisting the
    values with each sample gives historical results a stable snapshot while
    avoiding an external request on every scheduled measurement.
    """
    global _cached_identity, _cached_at
    now = time.monotonic()
    with _cache_lock:
        if not force and _cached_identity is not None and now - _cached_at < cache_seconds:
            result = deepcopy(_cached_identity)
            if isp_hint and not result.get("isp"):
                result["isp"] = isp_hint
            return result

    fields = "success,ip,country,country_code,region,city,latitude,longitude,connection.isp,connection.org,connection.asn"
    result = {
        "public_ip": None,
        "country": None,
        "country_code": None,
        "city": None,
        "isp": isp_hint,
        "isp_organization": None,
        "asn": None,
        "isp_source": None,
        "isp_confidence": None,
        "isp_observed_at": None,
    }
    try:
        with urllib.request.urlopen(
            f"https://ipwho.is/?fields={fields}", timeout=timeout_seconds
        ) as response:
            raw = response.read(32769)
            if len(raw) > 32768:
                return result
            payload = json.loads(raw.decode("utf-8"))
        if not payload.get("success"):
            return result
        connection = payload.get("connection") or {}
        result.update(
            {
                "public_ip": payload.get("ip"),
                "country": payload.get("country"),
                "country_code": payload.get("country_code"),
                "city": payload.get("city"),
                "region": payload.get("region"),
                "latitude": payload.get("latitude"),
                "longitude": payload.get("longitude"),
                "isp": connection.get("isp") or connection.get("org") or isp_hint,
                "isp_organization": connection.get("org"),
                "asn": connection.get("asn"),
                "isp_source": "ipwho.is",
                "isp_confidence": "high",
                "isp_observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )
    except Exception:
        # Metadata enrichment must never interfere with the measurement path.
        return result

    with _cache_lock:
        _cached_identity = deepcopy(result)
        _cached_at = time.monotonic()
    return result


def clear_network_identity_cache() -> None:
    """Clear the process-local cache; intended for tests and diagnostics."""
    global _cached_identity, _cached_at
    with _cache_lock:
        _cached_identity = None
        _cached_at = 0.0
