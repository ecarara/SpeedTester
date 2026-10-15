# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Real Tk clicks and real authenticated IPC; OS elevation is covered in native CI.

Server replies are signed synthetic fixtures. No measurement runner is allowed.
Run with SPEEDTESTER_GUI_TESTS=1 on a graphical runner (Xvfb on Linux).
"""
import os
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from speedtester_protocol.desktop_controller import DesktopController
from speedtester_protocol.desktop_service import DesktopEngine
from speedtester_protocol.installation import protected_queue
from speedtester_protocol.local_control import ControlServer, ControlClient, serve_in_thread
from test_desktop_client import SignedProvider, configuration


@unittest.skipUnless(os.environ.get('SPEEDTESTER_GUI_TESTS') == '1', 'Requires a graphical desktop/Xvfb')
class GraphicalFlows(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from speedtester_protocol.desktop_gui import Installer
        self.tk = tk
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = SignedProvider()
        def no_measurements(*args, **kwargs):
            raise AssertionError('A GUI test must never run a measurement')
        self.engine = DesktopEngine(protected_queue(Path(self.temp.name).resolve()/'queue'),
            transport=self.provider, runner=no_measurements)
        self.controller = DesktopController(Path(self.temp.name).resolve()/'control')
        self.server = ControlServer(self.controller.key, self.engine.dispatch, port=0)
        self.thread = serve_in_thread(self.server)
        self.addCleanup(self.shutdown)
        self.controller.client = ControlClient(self.controller.key, port=self.server.server_port)
        self.native_calls = []
        def native(operation, purge=False):
            self.native_calls.append((operation, purge))
            return {'ok':True, 'reboot_required':operation=='uninstall' and purge}
        self.controller.native = native
        self.window = Installer(self.controller)
        self.addCleanup(lambda: self.window.destroy() if self.window.winfo_exists() else None)
        self.dialogs = []
        self.confirm = True
        for name in ('showerror','showinfo','askyesno'):
            patcher = patch('speedtester_protocol.desktop_gui.messagebox.'+name,
                side_effect=lambda *a, _name=name, **kw: self.dialogs.append((_name, a)) or self.confirm)
            patcher.start();self.addCleanup(patcher.stop)
        patcher=patch('speedtester_protocol.desktop_gui.request_browser',return_value={'ok':True,'opened':False})
        self.browser=patcher.start();self.addCleanup(patcher.stop)
        self.window.update()

    def shutdown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(3)

    def widgets(self, parent=None):
        for child in (parent or self.window).winfo_children():
            yield child
            yield from self.widgets(child)

    def click(self, key, parent=None):
        matches=[w for w in self.widgets(parent) if isinstance(w,self.tk.Button) and w.cget('text')==self.window.t(key)]
        self.assertEqual(len(matches),1,(key,len(matches)))
        matches[0].invoke()
        self.settle()

    def settle(self):
        deadline=time.monotonic()+5
        while self.window.busy or not self.window.events.empty() or not self.window.browser_events.empty():
            self.window.update()
            self.assertLess(time.monotonic(),deadline,'UI worker did not complete')
            time.sleep(.01)
        self.window.update()

    def fill(self):
        self.window.contribute.set(True)
        profile=configuration()['profile']
        for key,value in {'origin':'https://server.example','operator':profile['operator'],
                'country':'ZZ','region':profile['region'],'city':profile['city']}.items():
            self.window.fields[key].set(value)
        self.window.access.set(self.window.t('fiber'))
        self.window.link.set(self.window.t('ethernet'))

    def test_install_optional_pair_cancel_return_and_all_languages_preserve_form(self):
        self.click('install')
        self.assertEqual(self.window.page,'configure')
        self.fill()
        for language in ('English','Español','Português'):
            self.window.languages.set(language);self.window.change_language();self.window.update()
            self.assertEqual(self.window.configuration()['profile']['access_type'],'fiber')
            self.assertEqual(self.window.configuration()['profile']['link_type'],'ethernet')
            self.assertEqual(self.window.fields['region'].get(),'Test region')
        self.click('data')
        self.assertIn('Sistema',self.window.disclosure_text.get('1.0','end'))
        self.assertEqual(self.window.disclosure_text.cget('state'),'disabled')
        self.click('close',self.window.disclosure_window)
        self.click('continue')
        self.assertEqual(self.native_calls,[('install',False)])
        self.assertEqual(self.window.page,'pair')
        self.click('pair')
        self.assertEqual(self.window.pairing['user_code'],'ABCDE-F2345')
        self.click('open_pair')
        self.assertEqual(self.window.portal_entry.get(),'https://server.example/pair?locale=pt-BR')
        self.click('copy_link',self.window.portal_window)
        self.assertEqual(self.window.clipboard_get(),self.window.portal_entry.get())
        self.click('close',self.window.portal_window)
        self.click('retry_pair')
        self.click('later')
        self.assertIsNone(self.window.pairing)
        self.assertEqual(self.window.page,'status')
        self.assertFalse(self.window.snapshot['paired'])
        self.click('copy_info')
        self.assertIn('SpeedTester Client',self.window.clipboard_get())
        self.assertNotIn(self.controller.key.hex(),self.window.clipboard_get())
        self.click('home');self.click('status');self.click('manage')
        self.assertEqual(self.window.configuration()['origin'],'https://server.example')
        self.window.contribute.set(False)
        self.click('save')
        self.assertFalse(self.window.snapshot['contribute'])
        self.assertEqual(self.provider.calls.count(('POST','/api/v1/measurement-grants')),0)

    def test_pair_approval_schedule_errors_enable_cancel_pause_and_account_origin(self):
        self.click('install');self.fill();self.click('continue');self.click('pair')
        self.provider.approved=True;self.engine.next_poll=0
        self.assertEqual(self.engine.tick(),'paired')
        self.window.poll_pairing();self.settle()
        self.assertTrue(self.window.snapshot['paired'])
        self.assertFalse(self.window.snapshot['measurements_enabled'])
        self.confirm=False;self.click('enable')
        self.assertFalse(self.window.snapshot['measurements_enabled'])
        self.confirm=True;self.provider.target_available=False;self.click('enable')
        self.assertEqual(self.dialogs[-1][0],'showerror')
        self.assertIn(self.window.t('no_target'),self.dialogs[-1][1])
        self.provider.target_available=True
        # Only synthetic target authorization; never tick with an enabled schedule.
        self.click('enable');self.assertTrue(self.window.snapshot['measurements_enabled'])
        self.click('pause');self.assertFalse(self.window.snapshot['measurements_enabled'])
        self.window.fields['origin'].set('https://wrong.example')
        self.click('account')
        self.assertEqual(self.window.portal_entry.get(),'https://server.example/account?locale=pt-BR')
        self.assertFalse(self.window.busy)
        self.click('close',self.window.portal_window)
        self.provider.blocked='account_suspended';self.click('enable')
        self.assertEqual(self.dialogs[-1][0],'showerror')
        self.assertFalse(self.engine.status()['measurements_enabled'])

    def test_opt_out_install_disconnects_an_existing_installation(self):
        self.engine.dispatch('configure',configuration())
        self.window.contribute.set(False)
        self.click('install');self.click('continue')
        self.assertEqual(self.window.page,'status')
        self.assertFalse(self.engine.status()['contribute'])
        self.assertEqual(self.provider.calls,[])

    def test_repair_uninstall_confirmation_preserve_purge_and_reboot_feedback(self):
        self.confirm=False;self.click('repair');self.assertEqual(self.native_calls,[])
        self.confirm=True;self.click('repair')
        self.assertEqual(self.native_calls,[('repair',False)])
        self.assertEqual(self.window.page,'status')
        self.click('home');self.click('uninstall')
        self.click('account');self.assertIn('/account?',self.window.portal_entry.get())
        self.click('close',self.window.portal_window)
        self.confirm=False;self.click('uninstall');self.assertEqual(len(self.native_calls),1)
        self.click('back');self.click('uninstall')
        self.confirm=True;self.click('uninstall')
        self.assertEqual(self.native_calls[-1],('uninstall',False))
        self.assertIn(self.window.t('preserved'),self.dialogs[-1][1])
        self.click('uninstall');self.window.purge.set(True);self.click('uninstall')
        self.assertEqual(self.native_calls[-1],('uninstall',True))
        self.assertIn(self.window.t('reboot'),self.dialogs[-1][1][1])
        self.assertEqual(self.window.page,'welcome')

    def test_invalid_input_browser_failure_and_callback_error_do_not_disable_later_actions(self):
        self.click('install');self.window.contribute.set(True);self.click('continue')
        self.assertEqual(self.dialogs[-1][0],'showerror');self.assertEqual(self.native_calls,[])
        self.window.fields['origin'].set('not https')
        self.click('data');self.click('data_portal',self.window.disclosure_window)
        self.assertEqual(self.dialogs[-1][0],'showerror');self.assertFalse(self.browser.called)
        self.click('close',self.window.disclosure_window);self.click('back')
        self.controller.native=lambda *a: (_ for _ in ()).throw(OSError('synthetic elevation denial'))
        self.click('repair');self.assertFalse(self.window.busy)
        self.window.work(lambda:{'ok':True},lambda r: (_ for _ in ()).throw(ValueError('synthetic rendering failure')))
        self.settle();self.assertEqual(self.dialogs[-1][0],'showerror')
        self.click('status');self.assertEqual(self.window.page,'status')
        self.window.fields['origin'].set('https://server.example')
        self.click('account');self.assertTrue(self.window.portal_window.winfo_exists())
        self.click('close',self.window.portal_window)
        self.assertFalse(self.window.busy)
