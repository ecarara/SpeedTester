# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Locate the Xlib locale payload belonging to the frozen Linux runtime."""
import os
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


def smoke_dead_keys(window):
    """Real X11 key events on an isolated CI display, never during installation."""
    import subprocess
    import time
    subprocess.run(['setxkbmap','-layout','br'],check=True,timeout=10)
    window.show('configure');window.update()
    assert 'host' not in window.fields and 'port' not in window.fields
    entry=window.entries['region']
    for expected,keys in [('São Paulo',['S','dead_tilde','a','o','space','P','a','u','l','o']),
                          ('ação',['a','ccedilla','dead_tilde','a','o']),
                          ('México',['M','dead_acute','e','x','i','c','o']),
                          ('España',['E','s','p','a','dead_tilde','n','a'])]:
        window.fields['region'].set('');entry.focus_force();window.update()
        subprocess.run(['xdotool','key','--clearmodifiers',*keys],check=True,timeout=10)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            window.update()
            if window.fields['region'].get()==expected:break
            time.sleep(.01)
        assert window.fields['region'].get()==expected, 'ABNT2 composition failed: '+repr(window.fields['region'].get())
