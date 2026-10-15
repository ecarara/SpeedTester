# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Visible browser-request outcomes, separate from installation operations."""
import webbrowser
from .client import HTTPS


def portal_url(origin, path, locale):
    if path not in {"/data", "/account"} or locale not in {"pt-BR", "en", "es"}:
        raise ValueError("invalid_portal_link")
    return HTTPS(origin.strip()).origin + path + "?locale=" + locale


def request_browser(url, *, preview=False, opener=None):
    # Preview does not launch applications or perform network activity.
    if preview:
        return {"ok": True, "opened": False}
    try:
        opened = bool((opener or webbrowser.open)(url, new=2))
    except Exception:
        # Browser/desktop errors must lead to a visible, copyable fallback.
        opened = False
    return {"ok": True, "opened": opened}
