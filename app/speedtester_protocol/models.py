# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Strict per-metric records; unavailable values never become zero."""
from typing import Annotated, Literal
from uuid import UUID
from .profile_text import normalize_text
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
METRICS = {
    "download": ("bit/s", 10**12, "higher"), "upload": ("bit/s", 10**12, "higher"),
    "latency": ("us", 600_000_000, "lower"), "jitter": ("us", 600_000_000, "lower"),
    "packet_loss": ("ppm", 1_000_000, "lower"), "duration": ("ms", 300_000, "context"),
    "transfer": ("byte", 10**12, "context"), "tcp_retransmits": ("count", 10**9, "context"),
}
REQUIRED_METRICS = frozenset(METRICS)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Profile(StrictModel):
    version: int = Field(ge=1)
    operator: str = Field(min_length=1, max_length=100)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    region: str = Field(max_length=80)
    city: str = Field(max_length=80)
    access_type: Literal["fiber", "coaxial", "radio", "satellite", "cellular", "dsl", "other", "unknown"]
    link_type: Literal["ethernet", "wifi"]
    contracted_download_bps: int | None = Field(default=None, gt=0, le=10**12)
    contracted_upload_bps: int | None = Field(default=None, gt=0, le=10**12)

    @field_validator("operator", "country_code", "region", "city", mode="before")
    @classmethod
    def clean_text(cls, value):
        return normalize_text(value)


class ScheduleSlot(StrictModel):
    local_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    quadrant: Literal["madrugada", "manha", "tarde", "noite"]
    index: int = Field(ge=1, le=2)


class GrantRequest(StrictModel):
    request_id: Identifier
    profile: Profile
    runner: Literal["iperf3", "ookla", "fast"]
    schedule_slot: ScheduleSlot | None = None


class Grant(StrictModel):
    protocol_version: Literal["1"] = "1"
    attempt_id: Identifier
    client_id: Identifier
    profile_digest: Digest
    legal_digest: Digest
    runner: Literal["iperf3", "ookla", "fast"]
    target_id: str = Field(min_length=1, max_length=80)
    target_scope: Literal["unconfirmed", "lan", "external-controlled"]
    nonce: str = Field(min_length=32, max_length=64)
    issued_at: int = Field(ge=0)
    start_before: int = Field(ge=0)
    submit_before: int = Field(ge=0)
    max_duration_ms: int = Field(ge=1, le=300000)
    max_bytes: int = Field(ge=1, le=10**12)
    previous_receipt: Digest | None = None


class Observation(StrictModel):
    protocol_version: Literal["1"] = "1"
    observation_id: Identifier
    attempt_id: Identifier
    metric: Literal["download", "upload", "latency", "jitter", "packet_loss", "duration", "transfer", "tcp_retransmits"]
    unit: str = Field(max_length=10)
    value: int | None = Field(ge=0, default=None)
    status: Literal["valid", "not-supported", "not-collected", "error"]
    method: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9:._-]+$")
    measured_at: int = Field(ge=0)
    profile_digest: Digest
    legal_digest: Digest
    nonce: str = Field(min_length=32, max_length=64)

    @model_validator(mode="after")
    def metric_semantics(self):
        unit, maximum, _ = METRICS[self.metric]
        if self.unit != unit or (self.value is not None and self.value > maximum):
            raise ValueError("metric unit or range mismatch")
        if (self.status == "valid") != (self.value is not None):
            raise ValueError("value only permitted for a valid observation")
        return self


class Manifest(StrictModel):
    protocol_version: Literal["1"] = "1"
    attempt_id: Identifier
    nonce: str = Field(min_length=32, max_length=64)
    profile_digest: Digest
    legal_digest: Digest
    previous_receipt: Digest | None = None
    observations: dict[str, Digest]
    @field_validator("observations")
    @classmethod
    def complete_metrics(cls, value):
        if set(value) != REQUIRED_METRICS:
            raise ValueError("all metric states must be accounted for")
        return value


class Envelope(StrictModel):
    payload: dict
    key_id: Digest
    signature: str = Field(min_length=86, max_length=86)


class Receipt(StrictModel):
    protocol_version: Literal["1"] = "1"
    attempt_id: Identifier
    observation_id: Identifier | None = None
    kind: Literal["observation", "manifest", "started"]
    digest: Digest
    accepted_at: int = Field(ge=0)


class Enrollment(StrictModel):
    possession_key: str = Field(min_length=43, max_length=43)
    measurement_key: str = Field(min_length=43, max_length=43)


class Acceptance(StrictModel):
    documents: dict[str, Digest]
    accept_terms: Literal[True]
    privacy_read: Literal[True]
    contribute: Literal[True]

    @field_validator("accept_terms","privacy_read","contribute",mode="before")
    @classmethod
    def actual_checkbox(cls,value):
        if type(value) is not bool or not value:raise ValueError("explicit true boolean required")
        return value


Secret = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{43}$")]


class PairingRequest(Enrollment):
    request_id: Identifier
    issued_at: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9 _.-]+$")


class Pairing(StrictModel):
    request_id: Identifier
    device_code: Secret
    user_code: str = Field(pattern=r"^[A-Z2-9]{5}-[A-Z2-9]{5}$")
    verification_uri: str = Field(max_length=200)
    expires_at: int = Field(ge=0)
    interval: int = Field(ge=5, le=60)
    nonce: Secret
    possession_key: str = Field(min_length=43, max_length=43)


class CredentialBundle(StrictModel):
    client_id: Identifier
    access_token: Secret
    refresh_token: Secret
    expires_at: int = Field(ge=0)
    refresh_expires_at: int = Field(ge=0)
    nonce: Secret
    possession_key: str = Field(min_length=43, max_length=43)
    request_id: Identifier


class RotationRequest(StrictModel):
    request_id: Identifier


class PairingApproval(StrictModel):
    user_code: str = Field(pattern=r"^[A-Z2-9]{5}-[A-Z2-9]{5}$")
    possession_fingerprint: Digest
    confirm: Literal[True]

    @field_validator("confirm", mode="before")
    @classmethod
    def actual_confirmation(cls, value):
        if type(value) is not bool or not value:
            raise ValueError("explicit confirmation required")
        return value


class SystemEnvironment(StrictModel):
    system: Literal["linux", "windows", "macos", "freebsd", "other"]
    distribution: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z0-9._-]+$")
    version: str | None = Field(default=None, min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._+-]+$")
    architecture: Literal["amd64", "arm64", "x86", "arm", "other"]


class EnvironmentReport(StrictModel):
    protocol_version: Literal["1"] = "1"
    environment_id: Identifier
    client_id: Identifier
    reported_at: int = Field(ge=0)
    environment: SystemEnvironment


class EnvironmentReceipt(StrictModel):
    protocol_version: Literal["1"] = "1"
    environment_id: Identifier
    client_id: Identifier
    digest: Digest
    accepted_at: int = Field(ge=0)


class MachineReport(StrictModel):
    request_id: Identifier
    client_id: Identifier
    machine_id: Digest
    basis: Literal["linux-machine-id", "windows-machine-guid", "macos-platform-uuid"]
    timezone: str = Field(min_length=1, max_length=100)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        from .central_slots import central_zone
        central_zone(value)
        return value


class MachinePolicy(StrictModel):
    request_id: Identifier
    client_id: Identifier
    machine_id: Digest
    timezone: str = Field(min_length=1, max_length=100)
    seed: Digest
    format: Literal["quadrants-server-v1"] = "quadrants-server-v1"
    timezone_database: Literal["2026.5"] = "2026.5"
    tests_per_quadrant: Literal[2] = 2
    tests_per_day: Literal[8] = 8
