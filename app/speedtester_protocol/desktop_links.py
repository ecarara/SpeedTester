# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Open system applications without leaking the frozen runtime library paths."""
import os
import platform
from pathlib import Path
import sys
import subprocess
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .client import HTTPS

_WINDOWS_LOADER_LOCK = threading.Lock()


def portal_url(origin, path, locale):
    if path not in {"/data", "/account"} or locale not in {"pt-BR", "en", "es"}:
        raise ValueError("invalid_portal_link")
    return HTTPS(origin.strip()).origin + path + "?locale=" + locale


def pairing_url(url, locale):
    parts = urlsplit(url)
    HTTPS(urlunsplit((parts.scheme, parts.netloc, "", "", "")))
    if parts.path != "/pair" or parts.fragment or locale not in {"pt-BR", "en", "es"}:
        raise ValueError("invalid_portal_link")
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "locale"]
    return urlunsplit(parts._replace(query=urlencode([*query, ("locale", locale)])))


def system_environment():
    environment = os.environ.copy()
    # PyInstaller changes the loader search path. xdg-open/gio and browsers must
    # use system libraries, not the Python/Tk libraries in the downloaded bundle.
    for key in ("LD_LIBRARY_PATH", "LIBPATH", "DYLD_LIBRARY_PATH"):
        original = environment.pop(key + "_ORIG", None)
        environment.pop(key, None)
        if original:
            environment[key] = original
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        # Tk's bundled Xlib locale loaders must not leak into GTK/desktop apps.
        for key in ("XLOCALEDIR", "XLOCALELIBDIR", "TCL_LIBRARY", "TK_LIBRARY"):
            value = environment.get(key)
            if value and Path(value).is_relative_to(bundle):
                environment.pop(key)
    return environment


def open_system_browser(url):
    system = platform.system()
    if system == "Windows":
        import ctypes
        # The bootloader's SetDllDirectory setting is inherited by ShellExecute.
        # Serialize changes and restore it so the running Client keeps its DLLs.
        with _WINDOWS_LOADER_LOCK:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
            kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            buffer = ctypes.create_unicode_buffer(32768)
            kernel.GetDllDirectoryW(len(buffer), buffer)
            previous = buffer.value
            if not kernel.SetDllDirectoryW(None):
                return False
            try:
                shell = ctypes.WinDLL("shell32", use_last_error=True)
                shell.ShellExecuteW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                    ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int]
                shell.ShellExecuteW.restype = ctypes.c_void_p
                result = shell.ShellExecuteW(None, "open", url, None, None, 1)
                return int(result or 0) > 32
            finally:
                kernel.SetDllDirectoryW(previous or None)
    command = ["/usr/bin/open", url] if system == "Darwin" else ["/usr/bin/xdg-open", url]
    result = subprocess.run(command, env=system_environment(), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, close_fds=True)
    return result.returncode == 0


def request_browser(url, *, preview=False, opener=None):
    if preview:
        return {"ok": True, "opened": False}
    try:
        opened = bool((opener or open_system_browser)(url))
    except Exception:
        opened = False
    # This means OS dispatch succeeded, never that the page loaded or logged in.
    return {"ok": True, "opened": opened}
