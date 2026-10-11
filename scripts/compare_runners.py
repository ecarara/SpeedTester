#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Execute fast.com, Ookla and iperf3 once each and print a comparison."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from collector.runner_dispatch import RUNNER_NAMES, run_named_runner
from shared.settings import load_settings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runners",
        default=",".join(RUNNER_NAMES),
        help="comma-separated runners (default: fast,ookla,iperf3)",
    )
    parser.add_argument(
        "--iperf3-server",
        default=None,
        help="temporary iperf3 server override for this comparison",
    )
    parser.add_argument(
        "--iperf3-port",
        type=int,
        default=None,
        help="temporary iperf3 port override for this comparison",
    )
    args = parser.parse_args()
    settings = load_settings()
    results = []
    for name in (item.strip().lower() for item in args.runners.split(",")):
        if not name:
            continue
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            result = run_named_runner(
                name,
                duration_seconds=settings.sample_duration_seconds,
                server_ids=settings.speedtest_server_ids,
                max_bytes=settings.max_bytes,
                bandwidth_contracted_mbps=settings.bandwidth_contracted_mbps,
                isp_lookup_enabled=settings.isp_lookup_enabled,
                isp_lookup_timeout_seconds=settings.isp_lookup_timeout_seconds,
                ookla_binary=settings.ookla_binary,
                iperf3_server=args.iperf3_server or settings.iperf3_server,
                iperf3_port=args.iperf3_port or settings.iperf3_port,
                iperf3_duration_seconds=settings.iperf3_duration_seconds,
                iperf3_parallel_streams=settings.iperf3_parallel_streams,
                measurement_timeout_seconds=settings.measurement_timeout_seconds,
            )
            results.append({
                "runner": name,
                "status": "success",
                "started_at": started_at,
                "result": asdict(result),
            })
        except Exception as exc:  # comparison should report all runners
            results.append({
                "runner": name,
                "status": "error",
                "started_at": started_at,
                "error": str(exc),
            })
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] == "success" for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
