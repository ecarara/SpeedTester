#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Check the installed package's real collector, without external measurements."""
import argparse
import sys
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app.resolve()))
    from shared.version import APP_VERSION
    from collector.iperf3_runner import IperfRunMetrics, run_iperf3
    from collector.network_metrics import PingMetrics
    assert APP_VERSION == args.version, (APP_VERSION, args.version)
    location = {'latitude': -23.55, 'longitude': -46.63, 'country_code': 'BR', 'city': 'São Paulo'}
    with patch('collector.iperf3_runner.resolve_network_identity', return_value=location), \
            patch('collector.iperf3_runner._run_once_metrics', return_value=IperfRunMetrics(900, 0, 1024)) as execute, \
            patch('collector.iperf3_runner.measure_ping', return_value=PingMetrics()):
        automatic = run_iperf3(server=None)
        assert automatic.target_selection == 'automatic'
        assert automatic.server_location == 'São Paulo, BR'
        assert execute.call_count == 2
        manual = run_iperf3(server='chosen.example', port=5300, isp_lookup_enabled=False)
        assert manual.target_selection == 'manual'
        assert execute.call_args.args[1:3] == ('chosen.example', 5300)
    print('installed-client-ok: version, automatic geography and manual override')


if __name__ == '__main__':
    main()
