# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Optional declared plan speeds; comparisons never rewrite captured records."""
from decimal import Decimal, InvalidOperation
import re
from .crypto import digest, unb64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def parse_mbps(value):
    value = value.strip()
    if not value:
        return None
    # Decimal separators accepted in all three interface languages; no ambiguous
    # thousands separators, exponents, NaN or silent truncation to integer bps.
    if not re.fullmatch(r"[0-9]{1,7}(?:[.,][0-9]{1,6})?", value):
        raise ValueError("invalid_plan_speed")
    try:
        bps = Decimal(value.replace(",", ".")) * 1_000_000
    except InvalidOperation as exc:
        raise ValueError("invalid_plan_speed") from exc
    if not 0 < bps <= 10**12 or bps != bps.to_integral_value():
        raise ValueError("invalid_plan_speed")
    return int(bps)


def format_mbps(bps):
    if bps is None:
        return ""
    return format(Decimal(bps) / 1_000_000, "f").rstrip("0").rstrip(".") if bps % 1_000_000 else str(bps // 1_000_000)


def comparison(queue, installed):
    if not installed:
        return {}
    profile = installed["profile"]
    result = {metric: {"contracted_bps": profile.get("contracted_" + metric + "_bps"),
        "measured_bps": None, "percent": None} for metric in ("download", "upload")}
    if not any(item["contracted_bps"] for item in result.values()):
        return result
    destination = digest({"origin": installed["origin"],
        "server_key": unb64(installed["server_key"]).hex(),
        "possession_key": Ed25519PrivateKey.from_private_bytes(bytes.fromhex(installed["possession_private"])).public_key().public_bytes_raw().hex()})
    # Match the versioned profile, not today's plan applied to an old result.
    current = digest(profile)
    with queue.connection() as conn:
        rows = conn.execute("SELECT id,ciphertext FROM entries WHERE destination=? AND status='accepted' ORDER BY rowid DESC LIMIT 128", (destination,)).fetchall()
    latest = None
    for identifier, ciphertext in rows:
        record = queue.open(ciphertext, identifier + ":" + destination)
        payload = record["envelope"]["payload"]
        if record["kind"] != "observation" or payload["profile_digest"] != current:
            continue
        if latest is None:
            latest = payload["attempt_id"]
        if payload["attempt_id"] != latest:
            continue
        metric = payload["metric"]
        if metric in result and payload["status"] == "valid" and payload["value"] is not None:
            item = result[metric]
            item["measured_bps"] = payload["value"]
            if item["contracted_bps"]:
                item["percent"] = float(Decimal(payload["value"]) * 100 / item["contracted_bps"])
    return result
