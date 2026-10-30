#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Run real iPerf port failover on loopback in a disposable container."""
import subprocess
import time

from collector.iperf3_runner import _measure_on_available_target, _run_once_metrics
from collector.target_selection import Target


def main():
    server = subprocess.Popen(
        ['iperf3', '-s', '-B', '127.0.0.1', '-p', '15202'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.5)
        target = Target('127.0.0.1', 15201, alternate_ports=(15202,))

        def execute(candidate, reverse, remaining, temporary_directory):
            options = {'timeout_seconds': remaining}
            if temporary_directory is not None:
                options['temporary_directory'] = temporary_directory
            return _run_once_metrics('iperf3', candidate.host, candidate.port, 1, 1,
                                     reverse=reverse, **options)

        selected, upload, download, attempts = _measure_on_available_target(
            (target,), execute, time.monotonic() + 25,
        )
        assert selected.port == 15202
        assert upload.speed_mbps > 0 and download.speed_mbps > 0
        assert [a['outcome'] for a in attempts] == ['error', 'selected']
        assert [a['server_name'] for a in attempts] == [
            'iperf3:127.0.0.1:15201', 'iperf3:127.0.0.1:15202',
        ]
        print('iperf3-port-failover-ok')
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == '__main__':
    main()
