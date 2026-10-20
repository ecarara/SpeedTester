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
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import webbrowser

from shared.user_config import config_path


DEFAULT_DASHBOARD_URL = "http://127.0.0.1:8000/"
DEFAULT_SERVICE_NAME = "speedtester-client.service"
DEFAULT_API_SERVICE_NAME = "speedtester-api.service"
LOCAL_PORT_RANGE = range(8000, 8101)


class LauncherError(RuntimeError):
    """Raised when the launcher configuration or operating-system action fails."""


def _config_file() -> Path:
    return config_path()


def _configured_local_port() -> int | None:
    """Read the persisted local API port without importing application settings."""
    path = _config_file()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if key.strip() == "API_PORT" and separator:
                port = int(value.strip())
                if 1 <= port <= 65535:
                    return port
    except (OSError, ValueError):
        return None
    return None


@dataclass(frozen=True)
class LauncherConfig:
    """Runtime configuration consumed by the desktop package."""

    dashboard_url: str = DEFAULT_DASHBOARD_URL
    service_name: str = DEFAULT_SERVICE_NAME
    api_service_name: str = DEFAULT_API_SERVICE_NAME

    @classmethod
    def from_environment(cls) -> "LauncherConfig":
        dashboard_url = os.environ.get("SPEEDTESTER_DASHBOARD_URL")
        if not dashboard_url:
            configured_port = os.environ.get("API_PORT")
            try:
                port = int(configured_port) if configured_port else _configured_local_port()
            except ValueError:
                port = None
            dashboard_url = f"http://127.0.0.1:{port or 8000}/"
        return cls(
            dashboard_url=dashboard_url,
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


def _local_endpoint_is_bound(url: str) -> bool:
    """Return whether a local TCP endpoint is occupied by any process."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        return False
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        family = socket.AF_INET6 if parsed.hostname == "::1" else socket.AF_INET
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.25)
            return probe.connect_ex((parsed.hostname, port)) == 0
    except (OSError, ValueError):
        return False


def _find_free_local_port() -> int:
    """Find a free loopback port for the local dashboard."""
    for port in LOCAL_PORT_RANGE:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise LauncherError("Não há uma porta local disponível para o dashboard do SpeedTester.")


def _persist_local_port(port: int) -> None:
    """Persist an automatically selected port while preserving user settings."""
    path = _config_file()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    except OSError as exc:
        raise LauncherError(f"Não foi possível atualizar a configuração local: {exc}") from exc

    replacement = f"API_PORT={port}"
    for index, line in enumerate(lines):
        if line.strip().startswith("API_PORT="):
            lines[index] = replacement
            break
    else:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(replacement)

    temporary = path.with_suffix(".env.tmp")
    try:
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise LauncherError(f"Não foi possível atualizar a configuração local: {exc}") from exc


def _url_with_port(url: str, port: int) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"
    return urllib.parse.urlunsplit(
        (parsed.scheme, f"{host}:{port}", parsed.path or "/", parsed.query, parsed.fragment)
    )


def _reload_user_manager() -> None:
    result = _run(["systemctl", "--user", "daemon-reload"])
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise LauncherError(detail or "Não foi possível recarregar o serviço do usuário.")


def ensure_dashboard_ready(config: LauncherConfig, timeout: float = 8.0) -> str:
    """Start the local API, when applicable, and wait for its health endpoint."""
    url = validate_dashboard_url(config.dashboard_url)
    if not _is_local_dashboard(url) or _dashboard_is_ready(url):
        return url

    if _local_endpoint_is_bound(url):
        if platform.system() != "Linux":
            raise LauncherError(
                "A porta do dashboard local está ocupada por outro processo: "
                f"{urllib.parse.urlsplit(url).netloc}."
            )
        alternate_port = _find_free_local_port()
        _persist_local_port(alternate_port)
        _reload_user_manager()
        url = _url_with_port(url, alternate_port)

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
            return url
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
    url = ensure_dashboard_ready(config)
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
