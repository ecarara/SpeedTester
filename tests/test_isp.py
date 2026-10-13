# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Verify the encrypted best-effort ISP fallback without external requests."""
import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch
from collector.network_identity import clear_network_identity_cache, resolve_network_identity
from collector.speedtest_runner import _resolve_isp


class ISPTests(unittest.TestCase):
    def tearDown(self):
        clear_network_identity_cache()

    def test_https_fallback_reads_connection_metadata(self):
        response = BytesIO(b'{"success":true,"connection":{"isp":"Example ISP"}}')
        with patch('aiohttp.ClientSession', side_effect=OSError('unavailable')), \
             patch('urllib.request.urlopen', return_value=response) as request:
            self.assertEqual(asyncio.run(_resolve_isp(5)), 'Example ISP')
        self.assertTrue(request.call_args.args[0].startswith('https://'))

    def test_service_error_is_not_stored_as_an_isp(self):
        response = BytesIO(b'{"success":false,"connection":{"isp":"invalid"}}')
        with patch('aiohttp.ClientSession', side_effect=OSError('unavailable')), \
             patch('urllib.request.urlopen', return_value=response):
            self.assertIsNone(asyncio.run(_resolve_isp(5)))

    def test_structured_identity_includes_city_country_and_asn_and_is_cached(self):
        response = BytesIO(
            b'{"success":true,"ip":"198.51.100.20","country":"Brazil",'
            b'"country_code":"BR","city":"Curitiba",'
            b'"connection":{"isp":"Vivo","org":"Telefonica Brasil","asn":"AS18881"}}'
        )
        with patch('urllib.request.urlopen', return_value=response) as request:
            identity = resolve_network_identity(5, force=True)
            cached = resolve_network_identity(5)
        self.assertEqual(identity['isp'], 'Vivo')
        self.assertEqual(identity['country'], 'Brazil')
        self.assertEqual(identity['city'], 'Curitiba')
        self.assertEqual(identity['asn'], 'AS18881')
        self.assertEqual(cached, identity)
        self.assertEqual(request.call_count, 1)
