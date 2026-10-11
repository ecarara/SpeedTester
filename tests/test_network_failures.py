# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Deterministic failure and conversion tests; no public speed tests run."""
import asyncio
import json
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from collector import connectivity, speedtest_runner as fast, runner_dispatch, ookla_runner
from collector.network_metrics import PingMetrics, measure_ping
from collector.iperf3_runner import run_iperf3, _run_once_metrics


class ConnectivityTests(unittest.TestCase):
    def test_missing_route_binary_and_unreachable_gateway_remain_unknown(self):
        with patch.object(connectivity.subprocess,'run',side_effect=FileNotFoundError):
            self.assertEqual(connectivity._default_route(),(None,None))
            self.assertFalse(connectivity._probe_gateway_icmp('192.0.2.1',1))
        self.assertFalse(connectivity._probe_gateway_icmp(None,1))
        self.assertEqual(connectivity._probe_host(None,(443,),1),[])
        with patch.object(connectivity.subprocess,'run',return_value=SimpleNamespace(stdout='default via 192.0.2.1 dev eth0',returncode=0)):
            self.assertEqual(connectivity._default_route(),('192.0.2.1','eth0'))
            self.assertTrue(connectivity._probe_gateway_icmp('192.0.2.1',1))

    def test_dns_failure_and_connection_failure_have_distinct_evidence(self):
        with patch.object(connectivity.socket,'getaddrinfo',side_effect=OSError('DNS unavailable')):
            self.assertFalse(connectivity._probe_dns_and_tcp('example.com',1)['dns'])
        addresses=[(2,1,6,'',('192.0.2.1',443))]
        socket=MagicMock();socket.__enter__.return_value.connect.side_effect=OSError('refused')
        with patch.object(connectivity.socket,'getaddrinfo',return_value=addresses),patch.object(connectivity.socket,'socket',return_value=socket):
            self.assertEqual(connectivity._probe_dns_and_tcp('example.com',1),{'dns':True,'reachable':False})
            socket.__enter__.return_value.connect.side_effect=None
            self.assertTrue(connectivity._probe_dns_and_tcp('example.com',1)['reachable'])
        with patch.object(connectivity.socket,'create_connection',side_effect=OSError):
            self.assertEqual(connectivity._probe_host('192.0.2.1',(80,443),1),[])
        with patch.object(connectivity.socket,'create_connection',return_value=MagicMock()):
            self.assertEqual(connectivity._probe_host('192.0.2.1',(80,443),1),[80,443])

    def test_ping_failure_missing_binary_and_decimal_comma(self):
        self.assertIsNone(measure_ping('').ping_ms)
        for error in (FileNotFoundError(),subprocess.TimeoutExpired('ping',1)):
            with patch('collector.network_metrics.subprocess.run',side_effect=error):
                self.assertIsNone(measure_ping('example.com').ping_ms)
        with patch('collector.network_metrics.subprocess.run',return_value=SimpleNamespace(stdout='',stderr='',returncode=1)):
            self.assertEqual(measure_ping('example.com').packet_loss_pct,100)
        with patch('collector.network_metrics.subprocess.run',return_value=SimpleNamespace(stdout='time=4,5 ms\n50,0% packet loss',stderr='',returncode=0)):
            self.assertEqual(measure_ping('example.com').ping_ms,4.5)


class RunnerFailureTests(unittest.TestCase):
    def test_iperf_errors_do_not_become_zero_bandwidth(self):
        for args in ({}, {'server':'example.com','duration_seconds':0},{'server':'example.com','timeout_seconds':0}):
            with self.assertRaises((RuntimeError,ValueError)):run_iperf3(**args)
        for failure in (FileNotFoundError(),subprocess.TimeoutExpired('iperf3',1)):
            with patch('collector.iperf3_runner.subprocess.run',side_effect=failure):
                with self.assertRaises(RuntimeError):_run_once_metrics('iperf3','example.com',5201,1,1,False)
        for status,output in ((1,'refused'),(0,'{}'),(0,'invalid json')):
            with patch('collector.iperf3_runner.subprocess.run',return_value=SimpleNamespace(returncode=status,stdout=output,stderr='')):
                with self.assertRaises(RuntimeError):_run_once_metrics('iperf3','example.com',5201,1,1,False)

    def test_dispatcher_passes_runner_specific_timeout_and_binary(self):
        args=dict(duration_seconds=1,server_ids=[1],max_bytes=10,bandwidth_contracted_mbps=1000,isp_lookup_enabled=False,isp_lookup_timeout_seconds=1)
        for name,function in (('fast','run_speedtest'),('ookla','run_ookla'),('iperf3','run_iperf3')):
            with patch.object(runner_dispatch,function,return_value='result') as execute:
                self.assertEqual(runner_dispatch.run_named_runner(name,**args),'result')
                if name=='iperf3':self.assertEqual(execute.call_args.kwargs['timeout_seconds'],60)
        with self.assertRaises(ValueError):runner_dispatch.run_named_runner('unknown',**args)

    def test_ookla_diagnostic_prefix_and_missing_metrics(self):
        payload={'type':'result','download':{'bandwidth':100},'upload':{'bandwidth':50},'server':{'host':'[2001:db8::1]:443'}}
        output='diagnostic { invalid }\n'+json.dumps(payload)
        with patch.object(ookla_runner.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=output,stderr='')),patch.object(ookla_runner,'measure_ping',return_value=PingMetrics(5,1,4,8,0)):
            self.assertEqual(ookla_runner.run_ookla().ping_ms,5)
        for failure in (FileNotFoundError(),subprocess.TimeoutExpired('speedtest',1)):
            with patch.object(ookla_runner.subprocess,'run',side_effect=failure):
                with self.assertRaises(RuntimeError):ookla_runner.run_ookla()
        for value in ('unparseable', '{}'):
            with self.assertRaises(RuntimeError):ookla_runner._extract_json(value)
        self.assertEqual(ookla_runner._server_host('example.com:443'),'example.com')
        self.assertEqual(ookla_runner._server_host('[2001:db8::1]:443'),'2001:db8::1')
        self.assertIsNone(ookla_runner._number('invalid'))
        with self.assertRaises(RuntimeError):ookla_runner._bits_to_mbps(None)


class FastTests(unittest.IsolatedAsyncioTestCase):
    def response(self, text='', data=None):
        response=MagicMock();response.__aenter__=AsyncMock(return_value=response);response.__aexit__=AsyncMock()
        response.text=AsyncMock(return_value=text);response.json=AsyncMock(return_value=data);response.read=AsyncMock(return_value=b'')
        return response

    async def test_fast_token_discovery_errors_and_urls(self):
        session=MagicMock();session.get.side_effect=[self.response('<script src="/example.js">'),self.response('token:"example-token"')]
        self.assertEqual(await fast._get_token(session),'example-token')
        for pages in ([self.response('no script')],[self.response('<script src="/example.js">'),self.response('no token')]):
            session.get.side_effect=pages
            with self.assertRaises(RuntimeError):await fast._get_token(session)
        session.get.side_effect=None;session.get.return_value=self.response(data=[{'url':'https://example.com'}])
        self.assertEqual(await fast._get_urls(session,'example-token'),['https://example.com'])

    async def test_pipeline_keeps_icmp_metrics_and_uses_fallback_when_unavailable(self):
        context=MagicMock();context.__aenter__=AsyncMock(return_value=MagicMock());context.__aexit__=AsyncMock()
        with patch.object(fast.aiohttp,'ClientSession',return_value=context),patch.object(fast,'_get_token',AsyncMock(return_value='example')),patch.object(fast,'_get_urls',AsyncMock(return_value=['https://example.com'])),patch.object(fast,'_measure_speed',AsyncMock(return_value=900)),patch.object(fast,'_measure_upload',AsyncMock(return_value=450)),patch.object(fast,'measure_ping',return_value=PingMetrics(5,1,4,8,0)):
            result=await fast._run_async(isp_lookup_enabled=False)
            self.assertEqual(result['download_mbps'],900)
            self.assertEqual(result['packet_loss_pct'],0)
            with patch.object(fast,'measure_ping',return_value=PingMetrics()),patch.object(fast,'_measure_ping',AsyncMock(return_value=(6,2))),patch.object(fast,'_resolve_isp',AsyncMock(return_value='Example ISP')):
                result=await fast._run_async()
                self.assertEqual(result['ping_ms'],6)
                self.assertEqual(result['isp'],'Example ISP')

    async def test_download_stream_eof_and_errors_preserve_actual_byte_count(self):
        response=self.response()
        async def chunks(_):
            yield b'1234';yield b'56'
        response.content.iter_chunked=chunks
        connection=fast._ConnTracker(response)
        self.assertEqual(await fast._pump(connection,'download',100,10**20),6)
        self.assertEqual(await fast._pump(connection,'download',100,10**20),0)
        response.release=AsyncMock()
        await fast._release(connection);await fast._release(connection)
        response.release.assert_awaited_once()
        async def broken(_):
            yield b'1234';raise OSError('connection lost')
        response.content.iter_chunked=broken;connection=fast._ConnTracker(response)
        self.assertEqual(await fast._pump(connection,'download',100,10**20),4)

    async def test_upload_counts_completed_posts_and_stops_on_edge_failure(self):
        session=MagicMock();session.post.return_value=self.response()
        with patch.object(fast,'time',SimpleNamespace(monotonic=Mock(side_effect=[0,2]))):
            self.assertEqual(await fast._upload_worker(session,'https://example.com',b'1234',1),4)
        session.post.side_effect=OSError('lost')
        with patch.object(fast,'time',SimpleNamespace(monotonic=Mock(return_value=0))):
            self.assertEqual(await fast._upload_worker(session,'https://example.com',b'1234',1),0)
        with self.assertRaises(RuntimeError):await fast._measure_upload(session,[],1,10,100)
        with patch.object(fast,'_upload_worker',AsyncMock(return_value=0)):
            with self.assertRaises(RuntimeError):await fast._measure_upload(session,['https://example.com'],1,10,100)
        with patch.object(fast,'_upload_worker',AsyncMock(return_value=1000)),patch.object(fast,'time',SimpleNamespace(monotonic=Mock(side_effect=[0,0,1]))):
            self.assertEqual(await fast._measure_upload(session,['https://example.com'],1,10,100),.008)

    async def test_latency_failure_is_unknown_instead_of_zero(self):
        with patch.object(fast,'_one_rtt',AsyncMock(side_effect=OSError)):
            self.assertEqual(await fast._measure_ping(attempts=2),(None,None))
        with patch.object(fast,'_one_rtt',AsyncMock(side_effect=[4,6,8])):
            self.assertEqual(await fast._measure_ping(attempts=3),(6,2))

    async def test_https_probe_requires_response_and_has_total_connection_timeout(self):
        reader=SimpleNamespace(read=AsyncMock(return_value=b'H'))
        writer=MagicMock();writer.drain=AsyncMock();writer.wait_closed=AsyncMock()
        with patch.object(fast.asyncio,'open_connection',AsyncMock(return_value=(reader,writer))):
            self.assertGreaterEqual(await fast._one_rtt('example.com',1),0)
            reader.read.assert_awaited_with(1)
            reader.read.return_value=b''
            with self.assertRaises(OSError):await fast._one_rtt('example.com',1)
            writer.close.assert_called()
        async def hung(*args,**kwargs):await asyncio.sleep(10)
        with patch.object(fast.asyncio,'open_connection',side_effect=hung):
            with self.assertRaises(TimeoutError):await fast._one_rtt('example.com',.01)
