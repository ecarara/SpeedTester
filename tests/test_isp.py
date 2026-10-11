# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Verify the encrypted best-effort ISP fallback without external requests."""
import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch
from collector.speedtest_runner import _resolve_isp


class ISPTests(unittest.TestCase):
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
