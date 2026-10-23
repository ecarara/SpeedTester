# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Packaged graphical app, native privileged helper, and service entry point."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
from .native_services import BOOTSTRAP, MARKER, native_layout


def configure_tls():
    # Frozen apps cannot depend on the build machine's Python CA directory.
    # Explicit administrator/test CA configuration is preserved.
    if getattr(sys, "frozen", False) and not os.environ.get("SSL_CERT_FILE") and not os.environ.get("SSL_CERT_DIR"):
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()


def agent_main(stop=None):
    from .desktop_service import run_service
    configure_tls()
    layout = native_layout()
    bootstrap = layout.state / BOOTSTRAP
    if bootstrap.stat().st_size > 4096:
        raise ValueError("invalid_service_configuration")
    configuration = json.loads(bootstrap.read_text())
    if set(configuration) != {"format", "control_key"} or configuration["format"] != MARKER:
        raise ValueError("invalid_service_configuration")
    key = bytes.fromhex(configuration["control_key"])
    if len(key) != 32:
        raise ValueError("invalid_control_key")
    os.chdir(layout.runtime)
    # No participant-controlled PATH, working directory or plugin directories.
    paths = [str(layout.executable.parent / "tools")]
    if os.name != "nt":
        paths.extend(("/usr/bin", "/bin", "/usr/sbin", "/sbin"))
    else:
        import win32api
        paths.append(win32api.GetSystemDirectory())
    os.environ["PATH"] = os.pathsep.join(paths)
    stop = stop or threading.Event()
    if threading.current_thread() is threading.main_thread():
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_args: stop.set())
    return run_service(layout.state / "queue", key, stop)


def native_helper_main(path):
    from .native_services import read_request, native_operation
    try:
        result = native_operation(read_request(path))
        return 10 if result.get("reboot_required") else 0
    except Exception as exc:
        # Bounded diagnostic codes and source locations, never exception
        # messages, request contents, paths, OS identities or credentials.
        import traceback
        frames = traceback.extract_tb(exc.__traceback__)[-8:]
        diagnostic = {"code": "native_operation_failed", "type": type(exc).__name__,
            "locations": [[Path(frame.filename).name, frame.name, frame.lineno] for frame in frames]}
        try:
            os.write(2, (json.dumps(diagnostic)+"\n").encode())
        except OSError:
            pass
        return 20


def smoke_browser_probe():
    probe = os.environ.get("SPEEDTESTER_BROWSER_PROBE", "")
    if probe:
        import re
        if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"
                or not re.fullmatch(r"(?a)\d{1,5}/[0-9a-f]{32}", probe)
                or not 1 <= int(probe.split("/")[0]) <= 65535):
            raise ValueError("invalid_ci_browser_probe")
        from . import desktop_links
        # Capture only the CI opener's bounded output for a loopback fixture.
        # This is not enabled by ordinary GUI or service invocations.
        original_run = desktop_links.subprocess.run
        def traced_run(*command, **options):
            options.update(stdout=desktop_links.subprocess.PIPE, stderr=desktop_links.subprocess.PIPE)
            result = original_run(*command, **options)
            os.write(2, ("ci_opener_exit:"+str(result.returncode)+"\n").encode()+result.stderr[-2048:])
            return result
        desktop_links.subprocess.run = traced_run
        # Report only a fixed outcome/class for this synthetic CI URL. The
        # external test server independently observes the real browser GET.
        try:
            dispatched = desktop_links.open_system_browser("http://127.0.0.1:" + probe)
            diagnostic = "ci_browser_dispatch:" + str(dispatched)
        except Exception as exc:
            diagnostic = "ci_browser_exception:" + type(exc).__name__
        try:
            os.write(2, (diagnostic+"\n").encode())
        except OSError:
            pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="CararaLab SpeedTester Client")
    from .version import build_label
    parser.add_argument("--version",action="version",version="SpeedTester Client "+build_label())
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--agent", action="store_true")
    modes.add_argument("--windows-service", action="store_true")
    modes.add_argument("--native-helper", type=Path)
    modes.add_argument("--preview", action="store_true", help="UI fixture; no installation, network or measurements")
    modes.add_argument("--ui-smoke", action="store_true", help="Disposable GUI smoke test; no installation or network")
    args = parser.parse_args(argv)
    if args.agent:
        return agent_main()
    if args.windows_service:
        from .windows_service import dispatch_service
        return dispatch_service()
    if args.native_helper:
        return native_helper_main(args.native_helper)
    from .input_methods import configure_input_methods
    configure_input_methods()
    from .desktop_controller import DesktopController, PreviewController
    from .desktop_gui import Installer
    controller = PreviewController() if args.preview or args.ui_smoke else DesktopController()
    window = Installer(controller)
    if args.ui_smoke:
        configure_tls()
        import ssl
        assert ssl.create_default_context().cert_store_stats()["x509_ca"] > 0
        window.smoke_test()
        smoke_browser_probe()
    else:
        window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
