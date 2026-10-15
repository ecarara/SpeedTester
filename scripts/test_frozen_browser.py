#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Prove the frozen app's system opener loads a page in a real browser on CI.

Only a loopback fixture page is served. No accounts, measurements or Server API.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise RuntimeError('Requires a disposable GitHub-hosted desktop')
    nonce=secrets.token_hex(16)
    loaded=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=='/'+nonce:
                loaded.set()
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'<title>SpeedTester browser acceptance fixture</title><p>Local test complete.</p>')
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    system=platform.system()
    bundle=ROOT/'dist/desktop/raw'/('SpeedTesterClient.app' if system=='Darwin' else 'SpeedTesterClient')
    executable=bundle/('Contents/MacOS/SpeedTesterClient' if system=='Darwin' else 'SpeedTesterClient.exe' if os.name=='nt' else 'SpeedTesterClient')
    try:
        with tempfile.TemporaryDirectory() as temporary:
            environment=os.environ.copy()
            environment['SPEEDTESTER_BROWSER_PROBE']=str(server.server_port)+'/'+nonce
            if system=='Linux':
                # xdg-open still performs OS dispatch; a real isolated Chrome
                # instance loads the loopback page rather than a fake opener.
                chrome=shutil.which('google-chrome') or shutil.which('chromium')
                assert chrome,'A real Chrome/Chromium browser is required'
                wrapper=Path(temporary)/'browser'
                import shlex
                wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(chrome)+' --headless --no-sandbox --disable-gpu --no-first-run --no-default-browser-check --user-data-dir='+shlex.quote(temporary+'/profile')+' "$@"\n')
                wrapper.chmod(0o700)
                environment['BROWSER']=str(wrapper)
                environment.pop('XDG_CURRENT_DESKTOP',None)
                environment.pop('DESKTOP_SESSION',None)
            result=subprocess.run([str(executable),'--ui-smoke'],env=environment,timeout=120,capture_output=True)
            assert result.returncode==0, f'Frozen smoke failed: {result.returncode}'
            assert loaded.wait(30),'OS opener returned but no real browser loaded the fixture page'
        report={'platform':system,'frozen_system_dispatch':True,'real_browser_page_loaded':True,
            'fixture':'loopback HTTP only','measurements':0}
        (ROOT/'dist/desktop/acceptance-browser.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
    finally:
        server.shutdown();server.server_close()

if __name__=='__main__':main()
