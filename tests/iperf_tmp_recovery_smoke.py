#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Exercise iPerf recovery in a disposable container with a tiny /tmp."""
import os
import subprocess
import time

from collector.iperf3_runner import run_iperf3


def main():
    server = subprocess.Popen(
        ['iperf3', '-s', '-B', '127.0.0.1', '-p', '15201'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, 'TMPDIR': '/dev/shm'},
    )
    try:
        time.sleep(0.5)
        result = run_iperf3(duration_seconds=1, server='127.0.0.1', port=15201,
                            parallel_streams=5, isp_lookup_enabled=False, timeout_seconds=30)
        assert len(result.target_attempts) == 2
        assert 'failed to read /dev/urandom' in result.target_attempts[0]['detail']
        assert result.target_attempts[1]['temporary_directory_recovery'] is True
        assert result.download_mbps > 0 and result.upload_mbps > 0
        assert result.duration_sec < 30
        print('iperf3-temp-recovery-ok')
    finally:
        server.terminate()
        server.wait(timeout=5)


if __name__ == '__main__':
    main()
