# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Bound actual incoming bytes before JSON parsing and limiter memory."""
from collections import deque

from starlette.responses import JSONResponse


def allow_request(buckets, client, now, limit, capacity):
    """Caller holds its lock; reject new clients when all slots are live."""
    if client not in buckets:
        if len(buckets) >= capacity:
            expired = [key for key, bucket in buckets.items()
                       if not bucket or now - bucket[-1] >= 60]
            for key in expired:
                del buckets[key]
        if len(buckets) >= capacity:
            return False
        buckets[client] = deque()
    bucket = buckets[client]
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


class RequestSizeLimit:
    """Buffer only bounded API payloads, including chunked/undeclared bodies."""
    def __init__(self, app, get_limit):
        self.app = app
        self.get_limit = get_limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        limit = self.get_limit()
        headers = dict(scope['headers'])
        declared = headers.get(b'content-length', b'0')
        if len(declared) > 20 or not declared.isdigit():
            return await JSONResponse({'detail': 'invalid content length'}, 400)(scope, receive, send)
        if int(declared) > limit:
            return await self.reject(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > limit:
                return await self.reject(scope, receive, send)
            body.extend(chunk)
            if not message.get('more_body', False):
                break
        consumed = False

        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        await self.app(scope, bounded_receive, send)

    async def reject(self, scope, receive, send):
        await JSONResponse({'detail': 'request body too large'}, 413)(scope, receive, send)
