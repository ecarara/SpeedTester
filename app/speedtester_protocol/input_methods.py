# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Locate the Xlib locale payload belonging to the frozen Linux runtime."""
import os
import subprocess
import time
from pathlib import Path
import sys


def configure_input_methods():
    if sys.platform!='linux' or not getattr(sys,'frozen',False):
        return
    base=Path(sys._MEIPASS)/'x11'
    # Keep the desktop's language, keyboard layout and chosen IME unchanged.
    # The bundled Ubuntu Xlib must not look for loaders in Ubuntu-only paths
    # when the client is run on Arch/Omarchy or another distribution.
    for name,directory in (('XLOCALEDIR',base/'locale'),('XLOCALELIBDIR',base/'modules')):
        if directory.is_dir():
            os.environ.setdefault(name,str(directory))



class DeadKeyComposer:
    """Compose raw Latin dead-key events only when XIM did not consume them.

    Already composed input, literal punctuation and pasted text are left to Tk.
    No keycodes/layout assumptions, input logging or global keyboard hooks.
    """
    accents = {
        "dead_grave": ("\u0300", "`"), "dead_acute": ("\u0301", "´"),
        "dead_circumflex": ("\u0302", "^"), "dead_tilde": ("\u0303", "~"),
        "dead_perispomeni": ("\u0303", "~"), "dead_diaeresis": ("\u0308", "¨"),
        "dead_cedilla": ("\u0327", "¸"),
    }
    modifiers = {"Shift_L", "Shift_R", "Caps_Lock", "Num_Lock", "ISO_Level3_Shift", "Mode_switch"}

    def __init__(self):
        self.pending = None

    def reset(self, _event=None):
        self.pending = None

    def feed(self, keysym, char, state=0):
        import unicodedata
        # Ctrl/Alt/Super shortcuts stay native; Mod5/AltGr is not a shortcut.
        if state & (4 | 8 | 64) or keysym.startswith(("Control_", "Alt_", "Meta_", "Super_")):
            self.reset()
            return None
        if keysym in self.modifiers:
            return None
        accent = self.accents.get(keysym)
        if accent:
            previous = self.pending
            self.pending = None if previous == accent else accent
            return previous[1] if previous else ""
        if self.pending is None:
            return None
        mark, literal = self.pending
        self.reset()
        if keysym in {"Escape", "BackSpace"}:
            return ""
        if len(char) != 1 or not char.isprintable():
            return None
        if char == " ":
            return literal
        # A working IME may deliver the composed character after a raw event.
        if mark in unicodedata.normalize("NFD", char):
            return char
        composed = unicodedata.normalize("NFC", char + mark)
        return composed if len(composed) == 1 else literal + char


def bind_dead_keys(entry):
    """A widget-local fallback on X11/XWayland; preserve working native IMEs."""
    if entry.tk.call("tk", "windowingsystem") != "x11":
        return None
    composer = DeadKeyComposer()
    def keypress(event):
        text = composer.feed(event.keysym, event.char, event.state)
        if text is None:
            return None
        if text:
            if entry.selection_present():
                entry.delete("sel.first", "sel.last")
            entry.insert("insert", text)
            entry.xview("insert")
        return "break"
    entry.bind("<KeyPress>", keypress, add="+")
    for sequence in ("<FocusOut>", "<ButtonPress>", "<<Paste>>", "<<Cut>>", "<<Clear>>"):
        entry.bind(sequence, composer.reset, add="+")
    return composer

def _type_smoke_keys(window, entry, keys, expected=None):
    if expected is not None:
        from .profile_text import uppercase_text
        expected = uppercase_text(expected)
    entry.delete(0, "end")
    entry.focus_force()
    window.update()
    subprocess.run(["xdotool", "key", "--clearmodifiers", *keys], check=True, timeout=10)
    deadline = time.monotonic() + (3 if expected is not None else .3)
    while time.monotonic() < deadline:
        window.update()
        if expected is not None and entry.get() == expected:
            return
        time.sleep(.01)
    if expected is not None:
        raise AssertionError("ABNT2 expected " + repr(expected) + "; got " + repr(entry.get()))



def smoke_dead_keys(window):
    """Real key events on disposable CI displays, including unavailable XIM."""
    import subprocess
    import time
    from tkinter import ttk
    subprocess.run(["setxkbmap", "-layout", "br"], check=True, timeout=10)
    fallback = os.environ.get("SPEEDTESTER_INPUT_SMOKE") == "fallback"
    if fallback:
        window.tk.call("tk", "useinputmethods", False)
    window.show("configure")
    window.update()
    assert "host" not in window.fields and "port" not in window.fields

    keys = ["S", "dead_tilde", "a", "o"]
    if fallback:
        # Establish that this display/input mode reproduces the actual failure.
        # Only this synthetic CI control widget has the fallback absent.
        control = ttk.Entry(window)
        # A synthetic control must remain visible regardless of form height.
        control.place(x=270, y=170, width=230, height=32)
        window.update()
        _type_smoke_keys(window, control, keys)
        assert control.get() == "S~ao", "Control did not reproduce raw dead keys: " + repr(control.get())
        control.destroy()
    entry = window.entries["region"]
    for expected, keys in [
        ("São Paulo", ["S", "dead_tilde", "a", "o", "space", "P", "a", "u", "l", "o"]),
        ("ação", ["a", "ccedilla", "dead_tilde", "a", "o"]),
        ("México", ["M", "dead_acute", "e", "x", "i", "c", "o"]),
        ("España", ["E", "s", "p", "a", "dead_tilde", "n", "a"]),
        ("Â à ü Ç", ["dead_circumflex", "A", "space", "dead_grave", "a", "space", "dead_diaeresis", "u", "space", "Ccedilla"]),
        ("~", ["dead_tilde", "space"]),
        ("S~ao", ["S", "dead_tilde", "space", "a", "o"]),
    ]:
        _type_smoke_keys(window, entry, keys, expected)
    # Pasting must never repair or reinterpret literal text.
    entry.delete(0, "end")
    window.clipboard_clear()
    window.clipboard_append("S~ao / São / ç / México")
    entry.event_generate("<<Paste>>")
    window.update()
    assert entry.get() == "S~AO / SÃO / Ç / MÉXICO"
    if fallback:
        _type_smoke_keys(window, entry, ["dead_tilde", "BackSpace", "a"], "a")
        _type_smoke_keys(window, entry, ["dead_acute", "Escape", "e"], "e")
        _type_smoke_keys(window, entry, ["a", "b"], "ab")
        entry.selection_range(0, "end")
        subprocess.run(["xdotool", "key", "dead_tilde", "a"], check=True, timeout=10)
        for _ in range(30):
            window.update()
            time.sleep(.01)
        assert entry.get() == "Ã"
        _type_smoke_keys(window, entry, ["dead_tilde"], "")
        city = window.entries["city"]
        _type_smoke_keys(window, city, ["a"], "a")
        _type_smoke_keys(window, entry, ["a"], "a")
    print("packaged_linux_dead_keys_ok: " + ("unavailable-XIM control=S~ao; fallback=SÃO" if fallback else "native-XIM"), flush=True)
