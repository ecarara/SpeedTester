# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""GUI-independent agent: optional enrollment, persistent queue, explicit schedule."""
import json
from pathlib import Path
import shutil
import threading
import time
from pydantic import Field, field_validator
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from .client import HTTPS, ProtocolError
from .cli import context, cycle, discover, exclusive
from .crypto import b64, digest, public_bytes
from .enrollment import PairingClient
from .environment import sync_environment
from .installation import protected_queue
from .local_control import ControlServer, serve_in_thread
from .models import Profile, StrictModel
from .runner import IperfRunner
from .schedule import DailySchedule, local_timezone, migrate_installation, policy
from zoneinfo import ZoneInfo

CONFIGURATION = "desktop:configuration"
ENABLED = "desktop:measurements_enabled"
MAX_DATABASE_BYTES = 128 * 1024 * 1024
MAX_PENDING_RECORDS = 10000


class DesktopConfiguration(StrictModel):
    origin: str = Field(max_length=200)
    profile: Profile
    # Older GUIs may send these fields; they are discarded and never used.
    host: str | None = Field(default=None, max_length=253, exclude=True)
    port: int = Field(default=5201, ge=1, le=65535, exclude=True)
    interval_hours: int | None = Field(default=None, ge=1, le=24, exclude=True)
    timezone: str = Field(default_factory=local_timezone, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value
    contribute: bool = False

    @field_validator("origin")
    @classmethod
    def https_origin(cls, value):
        return HTTPS(value).origin

    @field_validator("host")
    @classmethod
    def destination(cls, value):
        if value is not None:
            IperfRunner(value)
        return value


class DesktopEngine:
    def __init__(self, queue, *, transport=None, runner=None, clock=time.time, maintenance=False):
        self.queue, self.transport, self.runner, self.clock = queue, transport, runner, clock
        self.lock = threading.RLock()
        self.pairing = None
        self.next_poll = 0
        self.last_code = "maintenance" if maintenance else "ready"
        self.maintenance = maintenance
        self.last_tick = 0
        self.wake = threading.Event()
        installed=self.installation()
        if self.queue.state(CONFIGURATION) and installed and installed.get("target_mode")!="automatic":
            installed.update(target_mode="automatic")
            installed.pop("host",None)
            installed.pop("port",None)
            self.queue.state("installation",installed)
            self.queue.state(ENABLED,False)
        if installed:
            installed, migrated = migrate_installation(queue, installed)
            if migrated:
                self.queue.state(ENABLED, False)
            if self.queue.state(CONFIGURATION):
                configuration = self.configuration().model_copy(update={"timezone":installed["schedule"]["timezone"]})
                self.queue.state(CONFIGURATION, configuration.model_dump())
            DailySchedule(queue, installed["schedule"]).refresh(int(self.clock()))
        self.last_snapshot = self.status()

    def configuration(self):
        value = self.queue.state(CONFIGURATION)
        return DesktopConfiguration.model_validate(value) if value else None

    def installation(self):
        return self.queue.state("installation")

    def credentials(self):
        config = self.installation()
        return context(self.queue, config, self.transport) if config else (None, None)

    def counts(self):
        with self.queue.connection() as connection:
            rows = connection.execute("SELECT status,COUNT(*) FROM entries GROUP BY status").fetchall()
        return dict(rows)

    def status(self):
        configuration = self.configuration()
        credentials, _ = self.credentials()
        paired = bool(credentials and credentials.bundle)
        counts = self.counts()
        from .version import CLIENT_VERSION, BUILD_REVISION
        result = {"client_version":CLIENT_VERSION,"build_revision":BUILD_REVISION,"ok": True, "service": "running", "code": self.last_code,
            "configured": bool(configuration), "paired": paired,
            "contribute": bool(configuration and configuration.contribute),
            "measurements_enabled": bool(self.queue.state(ENABLED)) and not self.maintenance,
            "next_due": self.queue.state("next_due"), "pending": counts.get("pending", 0),
            "quarantined": counts.get("quarantined", 0), "database_bytes": self.queue.path.stat().st_size,
            "last_tick": self.last_tick, "configuration": configuration.model_dump() if configuration else None}
        if self.pairing and self.pairing.expires_at > int(self.clock()):
            result["pairing"] = {"user_code": self.pairing.user_code,
                "verification_uri": self.pairing.verification_uri, "expires_at": self.pairing.expires_at,
                "fingerprint": digest(credentials.identity)}
        self.last_snapshot = result
        return result

    def configure(self, arguments):
        configuration = DesktopConfiguration.model_validate(arguments)
        old = self.configuration()
        installed = self.installation()
        if installed and installed["origin"] != configuration.origin:
            raise ProtocolError("installation_server_changed")
        # Configuration never enrolls, discovers or sends OS metadata implicitly.
        self.queue.state(CONFIGURATION, configuration.model_dump())
        self.queue.state(ENABLED, False)
        self.pairing = None
        if installed:
            changed = {key: value for key, value in installed["profile"].items() if key != "version"} != configuration.profile.model_dump(exclude={"version"})
            profile = configuration.profile.model_copy(update={"version": installed["profile"]["version"] + 1}) if changed else Profile.model_validate(installed["profile"])
            installed.update(profile=profile.model_dump(), target_mode="automatic")
            installed.pop("interval", None)
            configuration=configuration.model_copy(update={"timezone":installed["schedule"]["timezone"]})
            self.queue.state(CONFIGURATION, configuration.model_dump())
            installed.pop("host", None)
            installed.pop("port", None)
            self.queue.state("installation", installed)
        self.last_code = "ready" if old else "configured"
        return self.status()

    def begin_pairing(self):
        configuration = self.configuration()
        if not configuration or not configuration.contribute:
            raise ProtocolError("contribution_not_selected")
        # Recover an active code instead of invalidating the portal's pending flow.
        if self.pairing and self.pairing.expires_at > int(self.clock()):
            return self.status()
        server = discover(configuration.origin, self.transport)
        installed = self.installation()
        if installed:
            if installed["origin"] != configuration.origin or installed["server_key"] != b64(public_bytes(server)):
                raise ProtocolError("installation_server_changed")
        else:
            installed = {"origin": configuration.origin, "server_key": b64(public_bytes(server)),
                "possession_private": Ed25519PrivateKey.generate().private_bytes_raw().hex(),
                "measurement_private": Ed25519PrivateKey.generate().private_bytes_raw().hex(),
                "profile": configuration.profile.model_dump(), "target_mode": "automatic",
                "schedule": policy(configuration.timezone)}
            self.queue.state("installation", installed)
        credentials, measurement = self.credentials()
        if credentials.bundle:
            # Existing identity can only continue if the central policy allows it.
            credentials.ensure_current(force=True)
            self.last_code = "paired"
        else:
            self.pairing = PairingClient(credentials, measurement).begin()
            self.next_poll = int(self.clock())
            self.last_code = "authorization_pending"
        return self.status()

    def dispatch(self, operation, arguments):
        if not self.lock.acquire(blocking=False):
            return {**self.last_snapshot, "busy": True} if operation == "status" else {"ok": False, "code": "local_busy"}
        try:
            return self._dispatch(operation, arguments)
        finally:
            self.lock.release()
            if operation != "status":
                self.wake.set()

    def _dispatch(self, operation, arguments):
        with self.lock:
            try:
                if operation == "configure":
                    return self.configure(arguments)
                if arguments:
                    raise ProtocolError("invalid_local_arguments")
                if operation == "status":
                    return self.status()
                if operation == "pair":
                    return self.begin_pairing()
                if operation == "cancel_pairing":
                    self.pairing = None
                    self.last_code = "pairing_cancelled"
                elif operation == "pause":
                    self.queue.state(ENABLED, False)
                elif operation == "disconnect":
                    self.queue.state(ENABLED, False)
                    configuration = self.configuration()
                    if configuration:
                        self.queue.state(CONFIGURATION, configuration.model_copy(update={"contribute": False}).model_dump())
                    self.pairing = None
                elif operation == "enable":
                    configuration = self.configuration()
                    credentials, _ = self.credentials()
                    if not configuration or not configuration.contribute or not credentials or not credentials.bundle:
                        raise ProtocolError("pairing_required")
                    # Validate authorization and policy without probing any test server.
                    credentials.ensure_current(force=True)
                    from .targets import obtain_target
                    obtain_target(credentials.client(), credentials.bundle.client_id)
                    if not self.runner and not shutil.which("iperf3"):
                        raise ProtocolError("iperf3_required")
                    self.maintenance = False
                    DailySchedule(self.queue,self.installation()["schedule"]).refresh(int(self.clock()),activate=True)
                    self.queue.state(ENABLED, True)
                else:
                    raise ProtocolError("unknown_local_operation")
                return self.status()
            except ProtocolError as exc:
                # The stable code is displayed locally; secrets/bodies never leave the service.
                self.last_code = exc.code if exc.code in DISPLAY_CODES else "server_rejected"
                return {"ok": False, "code": self.last_code}

    def tick(self):
        with self.lock:
            self.last_tick = int(self.clock())
            configuration = self.configuration()
            if not configuration or not configuration.contribute:
                return "idle"
            credentials, measurement = self.credentials()
            if self.pairing and self.last_tick >= self.next_poll:
                if self.pairing.expires_at <= self.last_tick:
                    self.pairing = None
                    self.last_code = "pairing_expired"
                    return self.last_code
                self.next_poll = self.last_tick + self.pairing.interval
                try:
                    PairingClient(credentials, measurement).poll(self.pairing)
                except ProtocolError as exc:
                    if exc.code == "authorization_pending":
                        return exc.code
                    if exc.code == "slow_down":
                        self.next_poll += 5
                        return exc.code
                    raise
                self.pairing = None
                DailySchedule(self.queue,self.installation()["schedule"]).refresh(self.last_tick,activate=True)
                sync_environment(credentials, measurement)
                self.last_code = "paired"
                return self.last_code
            if not credentials or not credentials.bundle:
                return "unpaired"
            if self.maintenance:
                return "maintenance"
            if not self.queue.state(ENABLED):
                credentials.ensure_current()
                self.last_code = "paused"
                return self.last_code
            counts = self.counts()
            if self.queue.path.stat().st_size >= MAX_DATABASE_BYTES or counts.get("pending", 0) >= MAX_PENDING_RECORDS:
                # Preserve all records; drain existing data without authorizing new tests.
                from .agent import CommunityAgent
                CommunityAgent(credentials.client(), self.queue, measurement,
                    Profile.model_validate(self.installation()["profile"]), "iperf3").sync()
                self.last_code = "storage_limit"
                return self.last_code
            try:
                self.last_code = cycle(self.queue, transport=self.transport, runner=self.runner, now=self.last_tick, clock=self.clock)
            except ProtocolError as exc:
                if exc.code not in {"test_target_unavailable", "invalid_test_target", "test_target_changed"}:
                    raise
                self.queue.state(ENABLED, False)
                self.last_code = exc.code
            return self.last_code


DISPLAY_CODES = frozenset({"ready", "configured", "paired", "paused", "waiting", "synchronized",
    "attempt_completed", "attempt_recovered", "schedule_slot_expired", "authorization_pending", "pairing_expired", "pairing_cancelled", "maintenance",
    "contribution_not_selected", "pairing_required", "iperf3_required", "installation_server_changed",
    "account_suspended", "account_disabled", "client_revoked", "token_revoked", "consent_required", "consent_withdrawn", "contribution_consent_required",
    "legal_acceptance_required", "terms_acceptance_required", "legal_context_changed", "server_rejected", "storage_limit",
    "test_target_unavailable", "invalid_test_target", "test_target_changed", "local_or_network_failure", "unknown_local_operation", "invalid_local_arguments", "local_busy"})


def run_service(state, key, stop=None, *, port=45873, maintenance=False):
    stop = stop or threading.Event()
    queue = protected_queue(state)
    with exclusive(queue):
        engine = DesktopEngine(queue, maintenance=maintenance)
        control = ControlServer(key, engine.dispatch, port)
        serve_in_thread(control)
        def on_stop():
            stop.wait()
            engine.wake.set()
        threading.Thread(target=on_stop, daemon=True).start()
        delay = 1
        try:
            while not stop.is_set():
                engine.wake.wait(delay)
                engine.wake.clear()
                if stop.is_set():
                    break
                try:
                    engine.tick()
                    engine.status()
                    delay = 5 if engine.pairing else 60
                except (OSError, ValueError, ProtocolError) as exc:
                    code = exc.code if isinstance(exc, ProtocolError) else "local_or_network_failure"
                    engine.last_code = code if code in DISPLAY_CODES else "server_rejected"
                    delay = min(300, max(5, delay * 2))
        finally:
            stop.set()
            control.shutdown()
            control.server_close()
