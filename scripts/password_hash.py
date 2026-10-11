#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Read a password interactively and print its scrypt hash for the env file."""
import getpass
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from api.auth import password_hash

if __name__ == '__main__':
    first = getpass.getpass('Senha (mínimo 12 caracteres): ')
    second = getpass.getpass('Repita a senha: ')
    if len(first) < 12 or first != second:
        sys.exit('Senha curta ou confirmação diferente')
    print("API_VIEWER_PASSWORD_HASH='" + password_hash(first) + "'")
