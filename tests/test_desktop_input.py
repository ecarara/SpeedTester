# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Input regression: raw dead keys, working IMEs, editing and literal data."""
from types import SimpleNamespace
import unittest
from speedtester_protocol.input_methods import DeadKeyComposer, bind_dead_keys


class Entry:
    def __init__(self, system='x11'):
        self.tk = SimpleNamespace(call=lambda *_args: system)
        self.bindings = {}
        self.text = 'Original'
        self.selected = False
    def bind(self, event, callback, add=None):
        self.bindings[event] = callback
    def selection_present(self):
        return self.selected
    def delete(self, start, end):
        assert (start, end) == ('sel.first', 'sel.last')
        self.text = ''
        self.selected = False
    def insert(self, index, text):
        assert index == 'insert'
        self.text += text
    def xview(self, index):
        assert index == 'insert'
    def key(self, keysym, char='', state=0):
        return self.bindings['<KeyPress>'](SimpleNamespace(keysym=keysym, char=char, state=state))


class InputTests(unittest.TestCase):
    def test_raw_dead_keys_compose_both_cases_for_supported_languages(self):
        compose = DeadKeyComposer()
        for key, char, expected in [('dead_tilde','a','ã'),('dead_tilde','A','Ã'),
                ('dead_tilde','n','ñ'),('dead_acute','e','é'),('dead_acute','E','É'),
                ('dead_circumflex','a','â'),('dead_grave','a','à'),
                ('dead_diaeresis','u','ü'),('dead_cedilla','c','ç')]:
            self.assertEqual(compose.feed(key,'~'), '')
            self.assertEqual(compose.feed(char,char), expected)

    def test_working_ime_commits_and_literal_punctuation_are_not_reinterpreted(self):
        compose = DeadKeyComposer()
        for char in 'São México España ç S~ao':
            self.assertIsNone(compose.feed(char,char))
        self.assertIsNone(compose.feed('asciitilde','~'))
        compose.feed('dead_tilde','')
        self.assertEqual(compose.feed('atilde','ã'),'ã')

    def test_spacing_accents_and_unmatched_letters_preserve_intent(self):
        compose = DeadKeyComposer()
        compose.feed('dead_tilde','')
        self.assertEqual(compose.feed('space',' '),'~')
        compose.feed('dead_tilde','')
        self.assertEqual(compose.feed('dead_tilde',''),'~')
        self.assertIsNone(compose.feed('a','a'))
        compose.feed('dead_acute','')
        self.assertEqual(compose.feed('dead_tilde',''),'´')
        self.assertEqual(compose.feed('b','b'),'~b')

    def test_editing_keys_cancel_composition_and_shift_does_not(self):
        compose = DeadKeyComposer()
        for key in ('Escape','BackSpace','Left','Tab','Delete'):
            compose.feed('dead_tilde','')
            compose.feed(key,'')
            self.assertIsNone(compose.feed('a','a'))
        compose.feed('dead_tilde','')
        self.assertIsNone(compose.feed('Shift_L',''))
        self.assertEqual(compose.feed('A','A',1),'Ã')

    def test_shortcuts_cancel_but_altgr_does_not_count_as_a_shortcut(self):
        compose = DeadKeyComposer()
        for state in (4,8,64):
            compose.feed('dead_tilde','')
            self.assertIsNone(compose.feed('a','a',state))
            self.assertIsNone(compose.feed('e','e'))
        compose.feed('dead_tilde','',128)
        self.assertEqual(compose.feed('a','a'),'ã')

    def test_widget_inserts_one_composed_character_at_selection(self):
        entry = Entry()
        bind_dead_keys(entry)
        entry.selected = True
        self.assertEqual(entry.key('dead_tilde','~'),'break')
        self.assertEqual(entry.text,'Original')
        self.assertEqual(entry.key('a','a'),'break')
        self.assertEqual(entry.text,'ã')
        self.assertIsNone(entry.key('ccedilla','ç'))

    def test_focus_mouse_paste_and_cut_never_carry_accent_into_other_input(self):
        entry = Entry()
        bind_dead_keys(entry)
        for event in ('<FocusOut>','<ButtonPress>','<<Paste>>','<<Cut>>','<<Clear>>'):
            entry.key('dead_tilde','')
            entry.bindings[event](None)
            self.assertIsNone(entry.key('a','a'))
        self.assertEqual(entry.text,'Original')
        other = Entry()
        bind_dead_keys(other)
        entry.key('dead_acute','')
        self.assertIsNone(other.key('e','e'))

    def test_windows_and_macos_keep_their_native_input_untouched(self):
        for system in ('win32','aqua'):
            entry = Entry(system)
            self.assertIsNone(bind_dead_keys(entry))
            self.assertEqual(entry.bindings,{})


if __name__ == '__main__':
    unittest.main()
