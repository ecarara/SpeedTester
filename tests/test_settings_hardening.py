# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Secure API configuration contracts."""
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from shared.settings import load_settings


class SettingsHardeningTests(unittest.TestCase):
    def setUp(self):
        with patch('shared.settings.load_user_environment', lambda: None), \
             patch.dict(os.environ, {}, clear=True):
            self.settings = load_settings()

    def test_local_mode_requires_loopback_bind(self):
        with self.assertRaises(ValueError):
            replace(self.settings, api_require_login=False, api_bind_address='0.0.0.0')
        local = replace(self.settings, api_require_login=False, api_bind_address='127.0.0.1')
        self.assertFalse(local.api_require_login)

    def test_https_public_origin_requires_secure_cookie(self):
        with self.assertRaises(ValueError):
            replace(self.settings, api_public_origin='https://speedtester.example', api_cookie_secure=False)
        secured = replace(self.settings, api_public_origin='https://speedtester.example', api_cookie_secure=True)
        self.assertTrue(secured.api_cookie_secure)

    def test_public_origin_rejects_credentials_and_paths(self):
        for value in ('https://user:pass@example.test', 'https://example.test/admin'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.settings, api_public_origin=value, api_cookie_secure=True)


if __name__ == '__main__':
    unittest.main()
