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
        for name in ('showerror','showinfo'):
            patcher = patch('speedtester_protocol.desktop_gui.messagebox.'+name,
                side_effect=lambda *a, _name=name, **kw: self.dialogs.append((_name, a)) or self.confirm)
            patcher.start();self.addCleanup(patcher.stop)
        self.confirmation_patcher = patch('speedtester_protocol.desktop_gui.Installer.ask_confirmation', side_effect=lambda *a: self.confirm)
        self.confirmation_patcher.start();self.addCleanup(self.confirmation_patcher.stop)
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
        while self.window.busy or self.window.account_pending or not self.window.events.empty() or not self.window.browser_events.empty():
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

    def answer_confirmation(self, operation, decision, expected_title=None):
        errors = []
        deadline = time.monotonic() + 3
        def answer():
            popup = getattr(self.window, 'confirmation_window', None)
            if popup is None or not popup.winfo_exists() or not popup.winfo_viewable():
                if time.monotonic() < deadline:
                    self.window.after(20, answer)
                    return
                errors.append(AssertionError('Confirmation did not become visible'))
                return
            try:
                self.assertEqual(popup.title(), expected_title or self.window.t('enable'))
                labels = [w.cget('text') for w in self.widgets(popup) if isinstance(w, self.tk.Label)]
                buttons = [w for w in self.widgets(popup) if isinstance(w, self.tk.Button)]
                expected = {'pt-BR': ('Sim', 'Não'), 'en': ('Yes', 'No'), 'es': ('Sí', 'No')}[self.window.locale]
                self.assertEqual({w.cget('text') for w in buttons}, set(expected))
                for widget in self.widgets(popup):
                    self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), popup.winfo_rootx()+popup.winfo_width())
                    self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), popup.winfo_rooty()+popup.winfo_height())
                if expected_title is None:
                    self.assertEqual(labels, [self.window.t('enable_confirm')])
                    self.assertFalse(any(word in labels[0].lower() for word in ('orçamento', 'budget', 'presupuesto')))
                yes = next(w for w in buttons if w.cget('text') == expected[0])
                no = next(w for w in buttons if w.cget('text') == expected[1])
                if decision == 'close':
                    popup.tk.eval(popup.protocol('WM_DELETE_WINDOW'))
                elif decision in ('escape', 'enter_no', 'enter_yes'):
                    (yes if decision == 'enter_yes' else no).focus_force()
                    popup.update()
                    popup.event_generate('<Escape>' if decision == 'escape' else '<Return>')
                else:
                    (yes if decision == 'yes' else no).invoke()
            except Exception as exc:
                errors.append(exc)
            finally:
                if popup.winfo_exists():
                    popup.destroy()
        self.window.after(20, answer)
        self.click(operation)
        if errors:
            raise errors[0]

    def test_confirmation_buttons_and_cancel_keyboard_follow_selected_app_language(self):
        self.click('install');self.fill();self.click('continue')
        self.provider.approved=True;self.engine.next_poll=0
        self.assertEqual(self.engine.tick(),'paired')
        self.window.poll_pairing();self.settle()
        self.confirmation_patcher.stop()
        with patch('speedtester_protocol.desktop_gui.messagebox.askyesno', side_effect=AssertionError('Native buttons ignore app language')):
            for language in ('Português','English','Español'):
                self.window.languages.set(language);self.window.change_language();self.window.update()
                for decision in ('no','escape','close','enter_no'):
                    self.answer_confirmation('enable',decision)
                    self.assertFalse(self.engine.status()['measurements_enabled'])
                self.answer_confirmation('enable','enter_yes')
                self.assertTrue(self.window.snapshot['measurements_enabled'])
                self.click('pause')
                self.answer_confirmation('enable','yes')
                self.assertTrue(self.window.snapshot['measurements_enabled'])
                self.click('pause')
        self.assertEqual(self.provider.calls.count(('POST','/api/v1/measurement-grants')),0)

    def test_repair_and_uninstall_use_translated_confirmation_buttons(self):
        self.confirmation_patcher.stop()
        for language in ('Português','English','Español'):
            self.window.languages.set(language);self.window.change_language();self.window.update()
            self.answer_confirmation('repair','no',self.window.t('repair'))
            self.click('uninstall')
            self.answer_confirmation('uninstall','close',self.window.t('uninstall'))
            self.click('back')
        self.assertEqual(self.native_calls,[])
        self.assertEqual(self.provider.calls,[])

    def test_status_explains_completed_installation_paused_active_and_blocked_without_measurements(self):
        self.click('install');self.fill();self.click('continue')
        self.provider.approved=True;self.engine.next_poll=0
        self.assertEqual(self.engine.tick(),'paired')
        self.window.poll_pairing();self.settle()
        for language in ('Português','English','Español'):
            self.window.languages.set(language);self.window.change_language();self.window.update()
            labels=[w.cget('text') for w in self.widgets() if isinstance(w,self.tk.Label)]
            self.assertIn(self.window.t('setup_complete'),labels)
            self.assertIn(self.window.t('next_paused'),labels)
            self.assertNotIn(self.window.t('tests_active'),labels)
            calls=list(self.provider.calls)
            self.click('refresh_status')
            self.assertEqual(self.provider.calls,calls,'Refreshing local status must not contact the Server')
            self.assertGreater(self.window.snapshot['observed_at'],0)
            self.assertEqual(self.window.snapshot['accepted'],0)
            self.assertIsNone(self.window.snapshot['last_attempt_at'])
            self.provider.target_available=False;self.click('enable')
            self.click('refresh_status')
            labels=[w.cget('text') for w in self.widgets() if isinstance(w,self.tk.Label)]
            self.assertIn(self.window.t('last_notice')+' '+self.window.t('no_target'),labels)
            self.assertFalse(self.window.snapshot['measurements_enabled'])
            self.provider.target_available=True;self.click('enable')
            labels=[w.cget('text') for w in self.widgets() if isinstance(w,self.tk.Label)]
            self.assertIn(self.window.t('tests_active'),labels)
            self.assertIn(self.window.status_time(self.window.snapshot['next_due']),labels)
            self.assertIsNone(self.window.snapshot['problem'])
            self.window.geometry('960x780');self.window.update()
            for widget in self.widgets():
                if isinstance(widget,self.tk.Button):
                    self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),self.window.winfo_rooty()+self.window.winfo_height(),widget.cget('text'))
            self.click('pause')
        with patch.object(self.controller, 'call', side_effect=OSError('Synthetic stopped service')):
            self.click('refresh_status')
        labels=[w.cget('text') for w in self.widgets() if isinstance(w,self.tk.Label)]
        self.assertIn(self.window.t('service_unavailable'),labels)
        self.assertNotIn(self.window.t('tests_active'),labels)
        self.assertEqual(self.provider.calls.count(('POST','/api/v1/measurement-grants')),0)

    def test_install_optional_pair_cancel_return_and_all_languages_preserve_form(self):
        self.click('install')
        self.assertEqual(self.window.page,'configure')
        self.fill()
        for language in ('English','Español','Português'):
            self.window.languages.set(language);self.window.change_language();self.window.update()
            self.assertEqual(self.window.configuration()['profile']['access_type'],'fiber')
            self.assertEqual(self.window.configuration()['profile']['link_type'],'ethernet')
            self.assertEqual(self.window.fields['region'].get(),'TEST REGION')
        self.click('data')
        self.assertIn('Sistema',self.window.disclosure_text.get('1.0','end'))
        self.assertEqual(self.window.disclosure_text.cget('state'),'disabled')
        self.click('close',self.window.disclosure_window)
        self.click('continue')
        self.assertEqual(self.native_calls,[('install',False)])
        self.assertEqual(self.window.page,'pair')
        self.assertEqual(self.window.pairing['user_code'],'ABCDE-F2345')
        self.click('open_pair')
        portal=self.window.portal_window
        self.window.poll_pairing();self.settle()
        self.assertTrue(portal.winfo_exists(),'Polling must preserve the portal link and code screen')
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

    def test_opt_in_displays_code_before_any_browser_and_reopening_recovers_it(self):
        self.click('install');self.fill();self.click('continue')
        self.assertIsNotNone(self.window.pairing, 'Installing with pairing selected must show a code without another hidden step')
        code=self.window.pairing['user_code']
        self.assertTrue(any(isinstance(w,self.tk.Label) and w.cget('text')==code for w in self.widgets()))
        self.assertFalse(self.browser.called)
        self.window.geometry('960x780');self.window.update()
        for w in self.widgets():
            if isinstance(w,self.tk.Button):
                self.assertLessEqual(w.winfo_rooty()+w.winfo_height(),self.window.winfo_rooty()+self.window.winfo_height(),w.cget('text'))
        self.click('copy_code');self.assertEqual(self.window.clipboard_get(),code)
        before=self.provider.calls.count(('POST','/api/v1/pairings'))
        self.click('retry_pair')
        self.assertEqual(self.provider.calls.count(('POST','/api/v1/pairings')),before)
        self.window.destroy()
        from speedtester_protocol.desktop_gui import Installer
        self.window=Installer(self.controller);self.window.update()
        self.click('status');self.click('resume_pair')
        self.assertEqual(self.window.pairing['user_code'],code)
        self.assertEqual(self.provider.calls.count(('POST','/api/v1/pairings')),before)
        self.assertFalse(self.engine.status()['measurements_enabled'])

    def test_expired_code_is_removed_and_only_explicit_retry_generates_a_new_one(self):
        self.click('install');self.fill();self.click('continue')
        device_code=self.engine.pairing.device_code
        self.engine.pairing=self.engine.pairing.model_copy(update={'expires_at':1})
        credentials,_=self.engine.credentials()
        scope=credentials.scope+':pairing'
        pending=self.engine.queue.state(scope);pending['pairing']['expires_at']=1;pending['request']['issued_at']=1
        self.engine.queue.state(scope,pending)
        self.window.pairing['expires_at']=1
        self.click('open_pair')
        self.assertFalse(self.browser.called)
        self.assertIsNone(self.window.pairing)
        self.assertTrue(any(isinstance(w,self.tk.Label) and w.cget('text')==self.window.t('code_expired') for w in self.widgets()))
        before=self.provider.calls.count(('POST','/api/v1/pairings'))
        self.window.poll_pairing();self.settle()
        self.assertEqual(self.provider.calls.count(('POST','/api/v1/pairings')),before)
        self.click('pair')
        self.assertIsNotNone(self.window.pairing)
        self.assertNotEqual(self.engine.pairing.device_code,device_code)
        for language in ('English','Español','Português'):
            self.window.languages.set(language);self.window.change_language();self.window.update()
            self.click('copy_code');self.assertEqual(self.window.clipboard_get(),self.window.pairing['user_code'])
        self.assertFalse(self.engine.status()['measurements_enabled'])

    def test_code_generation_failure_is_visible_and_retry_recovers_without_reinstall(self):
        from speedtester_protocol.client import ProtocolError
        transport=self.engine.transport
        self.engine.transport=lambda *a: (_ for _ in ()).throw(ProtocolError('server_rejected'))
        self.click('install');self.fill();self.click('continue')
        self.assertEqual(self.window.page,'pair')
        self.assertIsNone(self.window.pairing)
        self.assertTrue(any(isinstance(w,self.tk.Label) and w.cget('text')==self.window.t('code_failed') for w in self.widgets()))
        self.assertFalse(self.browser.called)
        self.engine.transport=transport
        self.click('pair')
        self.assertIsNotNone(self.window.pairing)
        self.assertEqual(self.native_calls,[('install',False)])
        self.click('later');self.click('manage');self.click('save')
        self.assertIsNotNone(self.window.pairing)
        self.assertFalse(self.engine.status()['measurements_enabled'])

    def test_profile_fields_uppercase_typing_and_paste_but_preserve_url_and_accents(self):
        self.click('install');self.fill()
        values={'operator':'  opéradora   exemplo ','country':'br','region':'sa\u0303o paulo','city':'guarulhos'}
        for key,value in values.items():
            entry=self.window.entries[key]
            entry.delete(0,'end');entry.insert(0,value);self.window.update()
            self.assertEqual(entry.get(),__import__('unicodedata').normalize('NFC',value.upper()))
        self.window.fields['origin'].set('https://server.example')
        profile=self.window.configuration()['profile']
        self.assertEqual([profile[k] for k in ('operator','country_code','region','city')],['OPÉRADORA EXEMPLO','BR','SÃO PAULO','GUARULHOS'])
        self.assertEqual(self.window.fields['origin'].get(),'https://server.example')
        self.click('continue')
        self.assertEqual(self.engine.configuration().profile.region,'SÃO PAULO')
        self.assertFalse(self.engine.status()['measurements_enabled'])

    def test_pair_approval_schedule_errors_enable_cancel_pause_and_account_origin(self):
        self.click('install');self.fill();self.click('continue')
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
        runner=self.engine.runner
        self.engine.runner=None
        with patch('speedtester_protocol.desktop_service.shutil.which',return_value=None):
            self.click('enable')
        self.assertIn(self.window.t('no_runner'),self.dialogs[-1][1])
        self.assertFalse(self.engine.status()['measurements_enabled'])
        self.engine.runner=runner
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
        self.window.purge.set(True)
        self.click('back');self.click('uninstall')
        self.assertFalse(self.window.purge.get())
        self.confirm=True;self.click('uninstall')
        self.assertEqual(self.native_calls[-1],('uninstall',False))
        self.assertIn(self.window.t('preserved'),self.dialogs[-1][1])
        self.click('uninstall');self.window.purge.set(True);self.click('uninstall')
        self.assertEqual(self.native_calls[-1],('uninstall',True))
        self.assertIn(self.window.t('reboot'),self.dialogs[-1][1][1])
        self.assertEqual(self.window.page,'welcome')

    def test_every_access_and_link_option_survives_language_selection_events(self):
        from tkinter import ttk
        self.click('install');self.fill()
        for access in ('fiber','coaxial','radio','satellite','cellular','dsl','other','unknown'):
            for link in ('ethernet','wifi'):
                self.window.access.set(self.window.t(access));self.window.link.set(self.window.t(link))
                for language in ('English','Español','Português'):
                    choices=[w for w in self.widgets() if isinstance(w,ttk.Combobox) and tuple(w.cget('values'))==('Português','English','Español')]
                    self.assertEqual(len(choices),1)
                    choices[0].set(language);choices[0].event_generate('<<ComboboxSelected>>');self.window.update()
                    profile=self.window.configuration()['profile']
                    self.assertEqual((profile['access_type'],profile['link_type']),(access,link))
        checkboxes=[w for w in self.widgets() if isinstance(w,self.tk.Checkbutton)]
        self.assertEqual(len(checkboxes),1)
        checkboxes[0].invoke();self.assertIsNone(self.window.configuration())
        checkboxes[0].invoke();self.assertIsNotNone(self.window.configuration())

    def test_account_from_fresh_uninstaller_reads_persisted_server_without_reconfiguring(self):
        self.engine.dispatch('configure',configuration())
        self.assertEqual(self.window.snapshot,{})
        self.click('uninstall');self.click('account')
        self.assertEqual(self.window.portal_entry.get(),'https://server.example/account?locale=pt-BR')
        self.assertFalse(self.window.busy)
        self.assertEqual(self.native_calls,[])
        self.assertEqual(self.provider.calls,[])

    def test_browser_dispatch_cannot_hold_maintenance_busy_and_success_always_keeps_copy_link(self):
        import threading
        waiting=threading.Event();release=threading.Event()
        def slow(*a,**kw):
            waiting.set();release.wait(4)
            return {'ok':True,'opened':True}
        self.browser.side_effect=slow
        self.click('status');self.click('account')
        self.assertTrue(waiting.wait(1));self.assertFalse(self.window.busy)
        self.assertTrue(self.window.portal_window.winfo_exists())
        self.click('copy_link',self.window.portal_window)
        self.assertIn('/account?',self.window.clipboard_get())
        self.click('close',self.window.portal_window)
        self.click('home');self.click('repair')
        self.assertEqual(self.native_calls,[('repair',False)])
        release.set();self.settle()

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
