# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Canonical human-entered dimensions; never apply to URLs, keys or signatures."""
import unicodedata


def uppercase_text(value):
    return unicodedata.normalize('NFC', value.upper())


def normalize_text(value):
    if not isinstance(value, str):
        raise ValueError('profile text must be a string')
    if any(unicodedata.category(char).startswith('C') for char in value):
        raise ValueError('control characters are prohibited')
    return uppercase_text(' '.join(unicodedata.normalize('NFC', value).split()))
