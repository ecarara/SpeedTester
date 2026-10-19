# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Central configuration for the SpeedTester services."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from math import isfinite
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    """All tunable settings, sourced from environment variables."""

    # --- collector ---
    sample_interval_seconds: int
    sample_duration_seconds: int
    measurements_per_quadrant: int
    scheduler_late_tolerance_seconds: int
    timezone: str
    anomaly_retry_ratio: float
    anomaly_retry_min_download_mbps: Optional[float]
    speedtest_runner: str
    max_bytes: int
    speedtest_server_ids: Optional[list[int]]
    ookla_binary: str
    iperf3_server: Optional[str]
    iperf3_port: int
    iperf3_duration_seconds: int
    iperf3_parallel_streams: int
    measurement_timeout_seconds: int

    # --- ISP / contract ---
    bandwidth_contracted_mbps: Optional[float]
    isp_lookup_enabled: bool
    isp_lookup_timeout_seconds: float

    # --- db ---
    db_path: str

    # --- api ---
    api_host: str
    api_bind_address: str
    api_port: int
    api_admin_token: str
    api_require_admin_token: bool
    api_rate_limit_per_minute: int

    # --- operations ---
    collector_heartbeat_timeout_seconds: int
    alert_webhook_url: str
    alert_speed_threshold_pct: float
    alert_cooldown_seconds: int
    slot_lease_seconds: int = 300
    api_require_login: bool = True
    api_viewer_password_hash: str = ""
    api_admin_password_hash: str = ""
    api_session_seconds: int = 28800
    api_cookie_secure: bool = False
    measurement_target_controlled: bool = False
    api_max_body_bytes: int = 65536
    api_rate_limit_max_clients: int = 10000

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if not 60 <= self.api_session_seconds <= 86400:
            raise ValueError("api_session_seconds must be between 60 and 86400")
        if not 1024 <= self.api_max_body_bytes <= 1048576:
            raise ValueError('api_max_body_bytes must be between 1024 and 1048576')
        if not 1 <= self.api_rate_limit_max_clients <= 10000:
            raise ValueError('api_rate_limit_max_clients must be between 1 and 10000')
        positive = ('sample_interval_seconds', 'sample_duration_seconds', 'measurements_per_quadrant',
                    'max_bytes', 'iperf3_duration_seconds', 'iperf3_parallel_streams',
                    'measurement_timeout_seconds', 'api_rate_limit_per_minute',
                    'collector_heartbeat_timeout_seconds', 'isp_lookup_timeout_seconds')
        for name in positive:
            if not isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be positive and finite')
        if self.measurements_per_quadrant > 100:
            raise ValueError('measurements_per_quadrant must not exceed 100')
        for name in ('iperf3_port', 'api_port'):
            if not 1 <= getattr(self, name) <= 65535:
                raise ValueError(f'{name} must be a valid TCP port')
        if self.speedtest_runner not in {'iperf3', 'ookla', 'fast'}:
            raise ValueError('speedtest_runner must be iperf3, ookla or fast')
        if not 0 < self.anomaly_retry_ratio <= 1:
            raise ValueError('anomaly_retry_ratio must be between 0 and 1')
        if self.slot_lease_seconds < 60:
            raise ValueError('slot_lease_seconds must be at least 60')
        if self.scheduler_late_tolerance_seconds < 0 or self.alert_cooldown_seconds < 0:
            raise ValueError('tolerance and cooldown must not be negative')
        for value in (self.bandwidth_contracted_mbps, self.anomaly_retry_min_download_mbps):
            if value is not None and (not isfinite(value) or value <= 0):
                raise ValueError('contract and absolute retry threshold must be positive and finite')
        if not 0 < self.alert_speed_threshold_pct <= 100:
            raise ValueError('alert_speed_threshold_pct must be between 0 and 100')

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"Settings(interval={self.sample_interval_seconds}s, "
            f"duration={self.sample_duration_seconds}s, "
            f"db={self.db_path}, api={self.api_host}:{self.api_port})"
        )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid integer for {name}={raw!r}") from exc


def _env_float(name: str, default: Optional[float]) -> Optional[float]:
    """Return a float env var, or None when unset/blank."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid float for {name}={raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value not in {'1', 'true', 'yes', 'on', 'y', '0', 'false', 'no', 'off', 'n'}:
        raise ValueError(f'Invalid boolean for {name}')
    return value in {'1', 'true', 'yes', 'on', 'y'}


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default) or default


def _env_server_ids(name: str, default: list[int]) -> Optional[list[int]]:
    """Parse comma-separated Ookla server IDs.

    An empty value keeps the safe local default. Invalid values fail at
    startup instead of silently selecting an unexpected server.
    """
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    if raw.strip() == "":
        return list(default)
    try:
        return [int(value.strip()) for value in raw.split(",") if value.strip()]
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid server IDs for {name}={raw!r}") from exc


def load_settings() -> Settings:
    """Read environment variables and return validated application settings.

    ``%h`` is a systemd unit specifier, but values inside ``EnvironmentFile``
    are not unit files and must not rely on specifier expansion. Resolve it
    here so desktop upgrades always use a writable user-local database path.
    """
    configured_db_path = os.environ.get("DB_PATH")
    if configured_db_path:
        db_path = os.path.expanduser(
            configured_db_path.replace("%h", str(Path.home()), 1)
        )
    else:
        db_path = str(
            Path.home() / ".local" / "share" / "speedtester" / "data" / "speedtester.db"
        )
    return Settings(
        sample_interval_seconds=_env_int("SAMPLE_INTERVAL_SECONDS", 1800),
        sample_duration_seconds=_env_int("SAMPLE_DURATION_SECONDS", 30),
        measurements_per_quadrant=_env_int("MEASUREMENTS_PER_QUADRANT", 2),
        scheduler_late_tolerance_seconds=_env_int(
            "SCHEDULER_LATE_TOLERANCE_SECONDS", 900
        ),
        timezone=_env_str("TZ", "America/Sao_Paulo"),
        anomaly_retry_ratio=_env_float("ANOMALY_RETRY_RATIO", 0.5),
        anomaly_retry_min_download_mbps=_env_float(
            "ANOMALY_RETRY_MIN_DOWNLOAD_MBPS", None
        ),
        speedtest_runner=_env_str("SPEEDTEST_RUNNER", "iperf3").strip().lower(),
        max_bytes=_env_int("MAX_BYTES", 10_000_000),
        speedtest_server_ids=_env_server_ids("SPEEDTEST_SERVER_IDS", [29564]),
        ookla_binary=_env_str("OOKLA_BINARY", "speedtest"),
        iperf3_server=(os.environ.get("IPERF3_SERVER") or None),
        iperf3_port=_env_int("IPERF3_PORT", 5201),
        iperf3_duration_seconds=_env_int("IPERF3_DURATION_SECONDS", 10),
        iperf3_parallel_streams=_env_int("IPERF3_PARALLEL_STREAMS", 5),
        measurement_timeout_seconds=_env_int("MEASUREMENT_TIMEOUT_SECONDS", 60),
        bandwidth_contracted_mbps=_env_float("BANDWIDTH_CONTRACTED_MBP", None),
        isp_lookup_enabled=_env_bool("ISP_LOOKUP_ENABLED", True),
        isp_lookup_timeout_seconds=_env_float("ISP_LOOKUP_TIMEOUT_SECONDS", 5.0),
        db_path=db_path,
        api_host=_env_str("API_HOST", "0.0.0.0"),
        api_bind_address=_env_str("API_BIND_ADDRESS", "127.0.0.1"),
        api_port=_env_int("API_PORT", 8000),
        api_admin_token=os.environ.get("API_ADMIN_TOKEN", ""),
        api_require_admin_token=_env_bool("API_REQUIRE_ADMIN_TOKEN", True),
        api_rate_limit_per_minute=_env_int("API_RATE_LIMIT_PER_MINUTE", 120),
        collector_heartbeat_timeout_seconds=_env_int(
            "COLLECTOR_HEARTBEAT_TIMEOUT_SECONDS", 120
        ),
        alert_webhook_url=os.environ.get("ALERT_WEBHOOK_URL", "") or "",
        alert_speed_threshold_pct=_env_float("ALERT_SPEED_THRESHOLD_PCT", 80.0),
        alert_cooldown_seconds=_env_int("ALERT_COOLDOWN_SECONDS", 21600),
        slot_lease_seconds=_env_int("SLOT_LEASE_SECONDS", 300),
        # Desktop packages bind only to loopback and explicitly enable local
        # mode. Keep the secure server default everywhere else, while avoiding
        # a login screen for a single-user local dashboard.
        api_require_login=(
            False
            if _env_bool("SPEEDTESTER_LOCAL_MODE", False)
            else _env_bool("API_REQUIRE_LOGIN", True)
        ),
        api_viewer_password_hash=os.environ.get("API_VIEWER_PASSWORD_HASH", ""),
        api_admin_password_hash=os.environ.get("API_ADMIN_PASSWORD_HASH", ""),
        api_session_seconds=_env_int("API_SESSION_SECONDS", 28800),
        api_cookie_secure=_env_bool("API_COOKIE_SECURE", False),
        measurement_target_controlled=_env_bool("MEASUREMENT_TARGET_CONTROLLED", False),
        api_max_body_bytes=_env_int('API_MAX_BODY_BYTES', 65536),
        api_rate_limit_max_clients=_env_int('API_RATE_LIMIT_MAX_CLIENTS', 10000),
    )
