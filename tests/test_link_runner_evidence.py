# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Native source evidence and normalized results across supported collectors."""
import json
import subprocess
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from collector.iperf3_runner import IperfRunMetrics, _connected_address, _measurement_link, _run_once_metrics
from collector.network_link import NetworkLink
from collector.ookla_runner import run_ookla
from collector.speedtest_runner import run_speedtest


class LinkRunnerEvidenceTests(unittest.TestCase):
    def test_iperf_native_parallel_socket_addresses_are_parsed(self):
        payload = {'start': {'connected': [
            {'local_host':'192.0.2.10','remote_host':'198.51.100.1'},
            {'local_host':'192.0.2.10','remote_host':'198.51.100.1'}]},
            'end': {'sum_sent': {'bits_per_second':500_000_000,'bytes':1000}}}
        completed = subprocess.CompletedProcess([],0,json.dumps(payload),'')
        with patch('collector.iperf3_runner.subprocess.run',return_value=completed):
            result = _run_once_metrics('iperf3','target.example',5201,10,2,reverse=False)
        self.assertEqual((result.local_ip,result.remote_ip),('192.0.2.10','198.51.100.1'))
        self.assertEqual(result.speed_mbps,500)

    def test_conflicting_or_malformed_socket_addresses_do_not_guess(self):
        for payload in [{}, {'start':[]}, {'start':{'connected':{}}},
            {'start':{'connected':['bad']}}, {'start':{'connected':[{'local_host':'192.0.2.1'},{'local_host':'bad'}]}},
            {'start':{'connected':[{'local_host':'192.0.2.1'},{'local_host':'192.0.2.2'}]}}]:
            self.assertIsNone(_connected_address(payload,'local_host'))

    def test_iperf_uses_socket_source_and_reports_different_direction_links(self):
        upload = IperfRunMetrics(500,0,100,local_ip='192.0.2.10',remote_ip='198.51.100.1')
        download = IperfRunMetrics(900,0,100,local_ip='192.0.2.20',remote_ip='198.51.100.1')
        with patch('collector.iperf3_runner.detect_link', side_effect=[
            NetworkLink('wlp1','wifi','fixture','runner_address'),
            NetworkLink('enp1','ethernet','fixture','runner_address')]) as detector:
            result = _measurement_link(upload,download,'target.example',time.monotonic()+2,[])
        self.assertEqual((result.connection_type,result.interface),('mixed',None))
        self.assertEqual(detector.call_args_list[0].kwargs['local_ip'],'192.0.2.20')
        self.assertLessEqual(detector.call_args_list[0].kwargs['timeout_seconds'],2)
        self.assertLessEqual(detector.call_args_list[1].kwargs['timeout_seconds'],2)

    def test_different_source_families_on_same_adapter_are_not_mixed(self):
        upload = SimpleNamespace(local_ip='192.0.2.10',remote_ip='198.51.100.1')
        download = SimpleNamespace(local_ip='2001:db8::2',remote_ip='2001:db8::1')
        for other, expected in [(NetworkLink('en0','wifi'), 'wifi'), (NetworkLink(), 'unknown')]:
            with patch('collector.iperf3_runner.detect_link', side_effect=[NetworkLink('en0','wifi'),other]):
                self.assertEqual(_measurement_link(upload,download,'target.example',time.monotonic()+5,[]).connection_type,expected)

    def test_two_direction_inspections_share_the_five_second_budget(self):
        upload = SimpleNamespace(local_ip='192.0.2.10',remote_ip='198.51.100.1')
        download = SimpleNamespace(local_ip='192.0.2.20',remote_ip='198.51.100.1')
        now = [0.0]
        def inspect(**_kwargs):
            now[0] += 4.0
            return NetworkLink('same','wifi')
        with patch('collector.iperf3_runner.time.monotonic',side_effect=lambda: now[0]), \
             patch('collector.iperf3_runner.detect_link',side_effect=inspect) as detector:
            _measurement_link(upload,download,'target.example',60,[])
        self.assertEqual([call.kwargs['timeout_seconds'] for call in detector.call_args_list],[5,1])

    def test_ookla_provides_interface_and_literal_addresses_without_assuming_medium(self):
        payload = {'download':{'bandwidth':100_000_000},'upload':{'bandwidth':50_000_000},
            'interface':{'name':'en0','internalIp':'192.0.2.10'},'server':{'ip':'198.51.100.1'}}
        completed = subprocess.CompletedProcess([],0,json.dumps(payload),'')
        with patch('collector.ookla_runner.subprocess.run',return_value=completed), \
             patch('collector.ookla_runner.detect_link',return_value=NetworkLink('en0','wifi','fixture','runner_interface')) as detector:
            result = run_ookla()
        detector.assert_called_once_with(interface_hint='en0',local_ip='192.0.2.10',remote_ip='198.51.100.1')
        self.assertEqual(result.connection_type,'wifi')
        self.assertEqual(result.connection_evidence['interface'],'en0')

    def test_fast_runner_explicitly_marks_default_route_observation(self):
        metrics = dict(download_mbps=900,upload_mbps=500,ping_ms=5,jitter_ms=1,
            latency_min_ms=4,latency_max_ms=6,packet_loss_pct=0,tcp_retransmits=None,
            server_id=None,server_name='fast.com',country=None,isp=None)
        with patch('collector.speedtest_runner._run_async',new_callable=AsyncMock,return_value=metrics), \
             patch('collector.speedtest_runner.detect_link',return_value=NetworkLink('en0','wifi','fixture','default_route')):
            result = run_speedtest()
        self.assertEqual(result.connection_scope,'default_route')
        self.assertEqual(result.connection_type,'wifi')
