# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Cross-platform SpeedTester desktop launcher contract.

The launcher is intentionally small: it opens the local dashboard and exposes
safe, platform-specific controls for the background service. Packaging
projects can call this module without knowing whether the service uses
systemd-user, Task Scheduler, or launchd.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import platform
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser


DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8000/"
DEFAULT_SERVICE_NAME = "speedtester-client.service"
DEFAULT_API_SERVICE_NAME = "speedtester-api.service"


class LauncherError(RuntimeError):
    """Raised when the launcher configuration or operating-system action fails."""


@dataclass(frozen=True)
class LauncherConfig:
    """Runtime configuration consumed by the desktop package."""

    dashboard_url: str = DEFAULT_DASHBOARD_URL
    service_name: str = DEFAULT_SERVICE_NAME
    api_service_name: str = DEFAULT_API_SERVICE_NAME

    @classmethod
    def from_environment(cls) -> "LauncherConfig":
        return cls(
            dashboard_url=os.environ.get("SPEEDTESTER_DASHBOARD_URL", DEFAULT_DASHBOARD_URL),
            service_name=os.environ.get("SPEEDTESTER_SERVICE_NAME", DEFAULT_SERVICE_NAME),
            api_service_name=os.environ.get(
                "SPEEDTESTER_API_SERVICE_NAME", DEFAULT_API_SERVICE_NAME
            ),
        )


def validate_dashboard_url(value: str) -> str:
    """Accept only an HTTP(S) URL with a hostname for the dashboard."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LauncherError("SPEEDTESTER_DASHBOARD_URL deve ser uma URL HTTP(S) válida.")
    if parsed.username or parsed.password:
        raise LauncherError("A URL do dashboard não pode conter credenciais.")
    return value


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one fixed-argument OS command without invoking a shell."""
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise LauncherError(f"Comando indisponível: {command[0]}") from exc


def _is_local_dashboard(url: str) -> bool:
    """Return whether the URL is a local dashboard controlled by this package."""
    hostname = urllib.parse.urlsplit(url).hostname
    return hostname in {"127.0.0.1", "localhost", "::1"}


def _dashboard_health_url(url: str) -> str:
    """Build the local health URL without carrying dashboard query parameters."""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, "/health", "", "")
    )


def _dashboard_is_ready(url: str) -> bool:
    """Check the local API without following external redirects."""
    try:
        request = urllib.request.Request(
            _dashboard_health_url(url),
            headers={"Cache-Control": "no-cache", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=1.5) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def ensure_dashboard_ready(config: LauncherConfig, timeout: float = 8.0) -> None:
    """Start the local API, when applicable, and wait for its health endpoint."""
    url = validate_dashboard_url(config.dashboard_url)
    if not _is_local_dashboard(url) or _dashboard_is_ready(url):
        return

    try:
        ServiceController(config.api_service_name).execute("start")
    except LauncherError as exc:
        raise LauncherError(
            "O dashboard local não está disponível e o serviço "
            f"{config.api_service_name} não pôde ser iniciado: {exc}"
        ) from exc

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _dashboard_is_ready(url):
            return
        time.sleep(0.2)
    raise LauncherError(
        "O serviço local foi iniciado, mas não respondeu em "
        f"{_dashboard_health_url(url)}. Verifique o status de "
        f"{config.api_service_name}."
    )


class ServiceController:
    """Translate service actions to the native mechanism of each OS."""

    def __init__(self, service_name: str, system: str | None = None):
        if not service_name or any(char in service_name for char in "\r\n"):
            raise LauncherError("Nome de serviço inválido.")
        self.service_name = service_name
        self.system = system or platform.system()

    def _linux_command(self, action: str) -> list[str]:
        return ["systemctl", "--user", action, self.service_name]

    def _windows_command(self, action: str) -> list[str]:
        if action == "status":
            return ["schtasks", "/Query", "/TN", self.service_name, "/FO", "LIST"]
        return ["schtasks", "/" + {"start": "Run", "stop": "End"}[action], "/TN", self.service_name]

    def _macos_command(self, action: str) -> list[str]:
        target = f"gui/{os.getuid()}/{self.service_name}"
        if action == "status":
            return ["launchctl", "print", target]
        if action == "start":
            return ["launchctl", "kickstart", target]
        return ["launchctl", "kill", "SIGTERM", target]

    def _command(self, action: str) -> list[str]:
        if self.system == "Linux":
            return self._linux_command(action)
        if self.system == "Windows":
            return self._windows_command(action)
        if self.system == "Darwin":
            return self._macos_command(action)
        raise LauncherError(f"Sistema operacional não suportado: {self.system}")

    def execute(self, action: str) -> str:
        """Execute an action and return a stable status label."""
        if action not in {"status", "start", "stop"}:
            raise LauncherError(f"Ação de serviço inválida: {action}")
        result = _run(self._command(action))
        if action == "status":
            return "active" if result.returncode == 0 else "inactive"
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise LauncherError(detail or f"Não foi possível executar: {action}")
        return {"start": "started", "stop": "stopped"}[action]


def open_dashboard(config: LauncherConfig) -> None:
    """Open the configured dashboard without exposing credentials in logs."""
    url = validate_dashboard_url(config.dashboard_url)
    ensure_dashboard_ready(config)
    if not webbrowser.open(url, new=2):
        raise LauncherError("Não foi possível abrir o navegador padrão.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launcher desktop do SpeedTester")
    parser.add_argument(
        "action",
        nargs="?",
        choices=("open", "status", "start", "stop", "restart"),
        default="open",
        help="ação a executar (padrão: open)",
    )
    parser.add_argument("--url", help="URL HTTP(S) do dashboard")
    parser.add_argument("--service", help="nome do serviço nativo")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = LauncherConfig.from_environment()
        if args.url:
            config = LauncherConfig(args.url, config.service_name, config.api_service_name)
        if args.service:
            config = LauncherConfig(config.dashboard_url, args.service, config.api_service_name)
        if args.action == "open":
            open_dashboard(config)
            print("dashboard_opened")
        else:
            controller = ServiceController(config.service_name)
            if args.action == "restart":
                controller.execute("stop")
                controller.execute("start")
                print("service_restarted")
            else:
                print(controller.execute(args.action))
        return 0
    except LauncherError as exc:
        print(f"SpeedTester: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
