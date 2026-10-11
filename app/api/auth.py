# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Expiring, revocable SQLite sessions with two operator-configured roles."""
import hashlib
import hmac
import secrets
import time

COOKIE = 'speedtester_session'


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split('$')
        if algorithm != 'scrypt' or len(salt) != 32 or len(expected) != 128:
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def principal(request, settings, store):
    token = request.headers.get('X-Admin-Token', '')
    if token and settings.api_admin_token and hmac.compare_digest(token, settings.api_admin_token):
        return {'role': 'admin', 'username': 'admin', 'method': 'token'}
    cookie = request.cookies.get(COOKIE, '')
    if not cookie or len(cookie) > 256:
        return None
    with store._connection() as conn:
        row = conn.execute('SELECT * FROM auth_sessions WHERE token_hash=? AND expires_at>?',
                           (token_hash(cookie), time.time())).fetchone()
    if not row:
        return None
    result = dict(row)
    # Credential rotation revokes existing sessions without waiting for expiry.
    if result['credential_hash'] != credential_hash(result['role'], settings):
        return None
    result['method'] = 'session'
    return result


def credential_hash(role, settings):
    credential = settings.api_viewer_password_hash if role == 'viewer' else settings.api_admin_password_hash
    if role == 'admin' and not credential:
        credential = settings.api_admin_token
    return token_hash(credential)


def authenticate(username, password, settings):
    encoded = {'viewer': settings.api_viewer_password_hash, 'admin': settings.api_admin_password_hash}.get(username, '')
    if encoded and verify_password(password, encoded):
        return username
    if username == 'admin' and not encoded and settings.api_admin_token:
        if hmac.compare_digest(password, settings.api_admin_token):
            return 'admin'
    return None


def create_session(role, settings, store):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expires = time.time() + settings.api_session_seconds
    with store._connection() as conn:
        conn.execute('DELETE FROM auth_sessions WHERE expires_at<=?', (time.time(),))
        conn.execute('INSERT INTO auth_sessions VALUES (?,?,?,?,?,?)',
                     (token_hash(token), role, role, csrf, expires, credential_hash(role, settings)))
    return token, csrf, expires
