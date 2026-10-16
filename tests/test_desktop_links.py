# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""No browser, network, service changes or measurements in link regressions."""
import unittest
from unittest.mock import Mock, patch
from speedtester_protocol.desktop_links import portal_url, pairing_url, request_browser, system_environment, open_system_browser
from speedtester_protocol.disclosure import DISCLOSURE_CATALOG
from speedtester_protocol.desktop_text import TEXT

class PortalLinksTests(unittest.TestCase):
    def test_configured_origin_and_selected_locale_are_used_without_personal_data(self):
        for locale in ('pt-BR','en','es'):
            self.assertEqual(portal_url(' https://server.example:9443/ ', '/data',locale),
                'https://server.example:9443/data?locale='+locale)
            self.assertEqual(portal_url('https://server.example','/account',locale),
                'https://server.example/account?locale='+locale)

    def test_invalid_origins_and_non_portal_paths_are_rejected(self):
        for origin in ('','http://server.example','javascript:alert(1)','https://user:secret@server.example',
                'https://server.example/path','https://server.example?token=secret'):
            with self.subTest(origin=origin),self.assertRaises(ValueError):portal_url(origin,'/data','pt-BR')
        for path,locale in (('/logout','pt-BR'),('/data?token=x','en'),('/data','fr')):
            with self.assertRaises(ValueError):portal_url('https://server.example',path,locale)

    def test_preview_leaves_browser_untouched_and_requests_copyable_fallback(self):
        opener=Mock()
        result=request_browser('https://server.example/data?locale=pt-BR',preview=True,opener=opener)
        self.assertEqual(result,{'ok':True,'opened':False})
        opener.assert_not_called()

    def test_missing_browser_and_desktop_errors_request_fallback_instead_of_silent_success(self):
        for opener in (Mock(return_value=False),Mock(side_effect=OSError('desktop unavailable')),
                Mock(side_effect=RuntimeError('desktop unavailable'))):
            self.assertEqual(request_browser('https://server.example/data?locale=en',opener=opener),
                {'ok':True,'opened':False})
            opener.assert_called_once_with('https://server.example/data?locale=en')

    def test_success_is_only_a_browser_request_not_an_installation_or_consent(self):
        opener=Mock(return_value=True)
        self.assertEqual(request_browser('https://server.example/data?locale=es',opener=opener),
            {'ok':True,'opened':True})
        opener.assert_called_once()

    def test_local_inventory_and_browser_feedback_cover_all_three_languages(self):
        self.assertEqual(set(DISCLOSURE_CATALOG),{'pt-BR','en','es'})
        for locale,catalog in DISCLOSURE_CATALOG.items():
            self.assertTrue(catalog['intro'])
            self.assertEqual(len(catalog['sections']),8)
            self.assertTrue(all(title and description for title,description in catalog['sections']))
            for key in ('data','data_offline','data_portal','portal_link','copy_link','link_copied',
                    'browser_requested','browser_unavailable','invalid_portal'):
                self.assertTrue(TEXT[locale][key])
            self.assertTrue(all(catalog['publication'].values()))

    def test_pairing_url_preserves_query_without_duplicate_locale(self):
        self.assertEqual(pairing_url('https://server.example/pair?locale=en&flow=device','es'),
            'https://server.example/pair?flow=device&locale=es')
        for url in ('http://server.example/pair','https://server.example/logout','https://x.example/pair#fragment'):
            with self.assertRaises(ValueError): pairing_url(url,'pt-BR')

    def test_external_launch_restores_loader_environment_without_mutating_client(self):
        import os
        with patch.dict(os.environ, {'LD_LIBRARY_PATH':'/bundle/lib','LD_LIBRARY_PATH_ORIG':'/system/lib',
                'DYLD_LIBRARY_PATH':'/bundle/lib'},clear=True):
            env=system_environment()
            self.assertEqual(env, {'LD_LIBRARY_PATH':'/system/lib'})
            self.assertEqual(os.environ['LD_LIBRARY_PATH'],'/bundle/lib')

    def test_os_dispatch_has_no_shell_inherits_sanitized_environment_and_is_bounded(self):
        import subprocess
        for system,expected in (('Darwin','/usr/bin/open'),('Linux','/usr/bin/xdg-open')):
            with patch('platform.system',return_value=system), patch('subprocess.run',return_value=Mock(returncode=0)) as run:
                self.assertTrue(open_system_browser('https://server.example/account?locale=pt-BR'))
                self.assertEqual(run.call_args.args[0],[expected,'https://server.example/account?locale=pt-BR'])
                self.assertEqual(run.call_args.kwargs['timeout'],8)
                self.assertNotIn('shell',run.call_args.kwargs)
                run.side_effect=subprocess.TimeoutExpired('opener',8)
                self.assertFalse(request_browser('https://server.example/account')['opened'])

    def test_system_browser_does_not_load_the_clients_xlib_or_tk_payload(self):
        import os
        with patch('sys._MEIPASS','/application/bundle',create=True), patch.dict(os.environ,{
                'XLOCALEDIR':'/application/bundle/x11/locale','XLOCALELIBDIR':'/application/bundle/x11/modules',
                'TCL_LIBRARY':'/application/bundle/tcl','TK_LIBRARY':'/system/tk','LANG':'pt_BR.UTF-8',
                'XMODIFIERS':'@im=fcitx'},clear=True):
            env=system_environment()
            self.assertNotIn('XLOCALEDIR',env)
            self.assertNotIn('XLOCALELIBDIR',env)
            self.assertNotIn('TCL_LIBRARY',env)
            self.assertEqual(env['TK_LIBRARY'],'/system/tk')
            self.assertEqual(env['LANG'],'pt_BR.UTF-8')
            self.assertEqual(env['XMODIFIERS'],'@im=fcitx')
            self.assertIn('XLOCALEDIR',os.environ)
