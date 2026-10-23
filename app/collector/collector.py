# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""SpeedTester collector — the "robot".

Creates persistent daily slots and executes each due slot, persisting results to
SQLite via :class:`api.store.SampleStore`. Designed to run inside a container as
a long-lived foreground process (systemd keeps it alive on the host).
"""
from __future__ import annotations

import json
import signal
import sys
import time
from datetime import date, datetime, timedelta, timezone
from contextlib import contextmanager
from threading import Event, Thread
from typing import Optional

from api.store import MeasurementSlot, Sample, SampleStore
from collector.alert_delivery import deliver_due
from collector.anomaly import is_anomalous_download
from collector.connectivity import ConnectivitySnapshot, probe_connectivity
from collector.iperf3_runner import Iperf3Timeout
from collector.quadrants import local_date_now, plan_day_slots
from collector.runner_dispatch import run_named_runner
from shared.settings import Settings, load_settings
from shared.observation import start_observation


class ConnectivityFailure(RuntimeError):
    """A measurement failed because connectivity evidence changed mid-run."""

    def __init__(
        self,
        cause: str,
        origin: str,
        snapshot: ConnectivitySnapshot,
        note: str,
        classification_confidence: str,
    ):
        super().__init__(cause)
        self.cause = cause
        self.origin = origin
        self.snapshot = snapshot
        self.note = note
        self.classification_confidence = classification_confidence


class Collector:
    """Coordinate scheduling, diagnostics, runners and persistence.

    A collector instance owns no network server; it is a foreground worker
    intended to be supervised by Docker or systemd. All durable state belongs
    to :class:`api.store.SampleStore`, so a process restart can recover the
    existing plan instead of creating a new one.
    """

    def __init__(self, settings: Settings, store: SampleStore) -> None:
        """Create a collector with immutable configuration and a data store."""
        self.settings = settings
        self.store = store
        self._stop = False
        self._last_heartbeat_monotonic = 0.0
        self._current_slot = None
        self._last_attempt_id = None
        self._attempt_started_at = None

    def _handle_signal(self, signum, _frame):
        print(f"\n[collector] received signal {signum}, stopping gracefully")
        self._stop = True

    def _run_single(self, slot: dict) -> Optional[Sample]:
        """Execute one claimed slot and return its representative sample."""
        self._current_slot = slot
        self._last_attempt_id = None
        self._attempt_started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        connectivity = probe_connectivity()
        if not connectivity.gateway_reachable:
            return self._save_failure(
                slot,
                cause="gateway_unreachable",
                origin="INTERNAL",
                snapshot=connectivity,
            )
        if not connectivity.external_reachable:
            return self._save_external_failure(slot, connectivity, "external_unreachable")

        try:
            result = self._execute_speedtest_with_timeout_recovery()
        except ConnectivityFailure as exc:
            return self._save_failure(
                slot,
                cause=exc.cause,
                origin=exc.origin,
                snapshot=exc.snapshot,
                note=exc.note,
                classification_confidence=exc.classification_confidence,
            )
        except Exception as exc:
            return self._save_measurement_failure(slot, connectivity, exc)

        if is_anomalous_download(
            result.download_mbps,
            self.settings.bandwidth_contracted_mbps,
            self.settings.anomaly_retry_ratio,
            self.settings.anomaly_retry_min_download_mbps,
        ):
            self._mark_attempt("discarded", "Download below anomaly threshold; immediate retry selected")
            first_started_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            print(
                f"[collector] {first_started_at} "
                f"discarding anomalous first result down={result.download_mbps:.2f} Mbps; "
                "running immediate retry",
                flush=True,
            )
            try:
                result = self._execute_speedtest_with_timeout_recovery()
            except ConnectivityFailure as exc:
                return self._save_failure(
                    slot,
                    cause=exc.cause,
                    origin=exc.origin,
                    snapshot=exc.snapshot,
                    note=exc.note,
                    classification_confidence=exc.classification_confidence,
                )
            except Exception as exc:
                return self._save_measurement_failure(slot, connectivity, exc)
            retry_started_at = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            print(
                f"[collector] {retry_started_at} retry selected as representative "
                f"down={result.download_mbps:.2f} Mbps",
                flush=True,
            )

        self._mark_attempt("selected", "Representative result for the slot")
        started_at = self._attempt_started_at
        sample = Sample(
            started_at=started_at,
            download_mbps=round(result.download_mbps, 3),
            upload_mbps=round(result.upload_mbps, 3),
            ping_ms=round(result.ping_ms, 2) if result.ping_ms is not None else None,
            jitter_ms=(
                round(result.jitter_ms, 2)
                if result.jitter_ms is not None
                else None
            ),
            latency_min_ms=(
                round(getattr(result, "latency_min_ms", None), 2)
                if getattr(result, "latency_min_ms", None) is not None
                else None
            ),
            latency_max_ms=(
                round(getattr(result, "latency_max_ms", None), 2)
                if getattr(result, "latency_max_ms", None) is not None
                else None
            ),
            packet_loss_pct=(
                round(getattr(result, "packet_loss_pct", None), 2)
                if getattr(result, "packet_loss_pct", None) is not None
                else None
            ),
            tcp_retransmits=getattr(result, "tcp_retransmits", None),
            server_id=result.server_id,
            server_name=result.server_name,
            server_location=result.server_location,
            country=result.country,
            country_code=getattr(result, "country_code", None),
            city=getattr(result, "city", None),
            public_ip=getattr(result, "public_ip", None),
            interface=result.interface,
            isp=result.isp,
            isp_organization=getattr(result, "isp_organization", None),
            asn=getattr(result, "asn", None),
            isp_source=getattr(result, "isp_source", None),
            isp_confidence=getattr(result, "isp_confidence", None),
            isp_observed_at=getattr(result, "isp_observed_at", None),
            bandwidth_contracted_mbps=result.bandwidth_contracted_mbps,
            test_duration_sec=round(result.duration_sec, 1),
            slot_id=slot["id"],
            local_date=slot["local_date"],
            quadrant=slot["quadrant"],
            runner=self.settings.speedtest_runner,
            power_state="UNKNOWN",
            gateway_reachable=connectivity.gateway_reachable,
            external_reachable=connectivity.external_reachable,
            evidence_json=json.dumps(connectivity.evidence, sort_keys=True),
        )
        sample_id = self.store.add_sample(sample)
        self._evaluate_alerts(sample, sample_id)
        print(
            f"[collector] {started_at} "
            f"down={sample.download_mbps:.2f} Mbps "
            f"up={sample.upload_mbps:.2f} Mbps "
            f"ping={sample.ping_ms}ms  "
            f"(iface={sample.interface})  "
            f"in {sample.test_duration_sec}s",
            flush=True,
        )
        return sample

    def _execute_speedtest(self):
        """Dispatch one measurement using the configured runner."""
        self._attempt_started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            result = self._dispatch_speedtest()
        except Exception as exc:
            self._record_attempt("timeout" if isinstance(exc, Iperf3Timeout) else "error", str(exc)[:400], {})
            raise
        metrics = {name: getattr(result, name, None) for name in (
            "download_mbps", "upload_mbps", "ping_ms", "jitter_ms", "duration_sec",
            "latency_min_ms", "latency_max_ms", "packet_loss_pct", "tcp_retransmits",
            "server_name", "interface", "isp", "country", "country_code", "city",
            "public_ip", "isp_organization", "asn", "isp_source", "isp_confidence",
            "isp_observed_at", "transfer_bytes", "target_selection",
            "target_distance_km", "target_catalog_revision", "server_location")}
        self._record_attempt("candidate", None, metrics)
        return result

    def _record_attempt(self, outcome: str, reason: Optional[str], metrics: dict) -> None:
        record = getattr(self.store, "add_attempt", None)
        if record and self._current_slot:
            self._last_attempt_id = record(self._current_slot["id"], self._attempt_started_at,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), outcome, reason, metrics)

    def _mark_attempt(self, outcome: str, reason: str) -> None:
        mark = getattr(self.store, "mark_attempt", None)
        if mark and self._last_attempt_id is not None:
            mark(self._last_attempt_id, outcome, reason)

    def _dispatch_speedtest(self):
        return run_named_runner(
            self.settings.speedtest_runner,
            duration_seconds=self.settings.sample_duration_seconds,
            server_ids=self.settings.speedtest_server_ids,
            max_bytes=self.settings.max_bytes,
            bandwidth_contracted_mbps=self.settings.bandwidth_contracted_mbps,
            isp_lookup_enabled=self.settings.isp_lookup_enabled,
            isp_lookup_timeout_seconds=self.settings.isp_lookup_timeout_seconds,
            ookla_binary=self.settings.ookla_binary,
            iperf3_server=self.settings.iperf3_server,
            iperf3_port=self.settings.iperf3_port,
            iperf3_duration_seconds=self.settings.iperf3_duration_seconds,
            iperf3_parallel_streams=self.settings.iperf3_parallel_streams,
            iperf3_location=getattr(self.settings, "iperf3_location", None),
            measurement_timeout_seconds=getattr(
                self.settings, "measurement_timeout_seconds", 60
            ),
        )

    def _execute_speedtest_with_timeout_recovery(self):
        """Retry a timed-out iPerf3 attempt once as a fresh first attempt."""
        try:
            return self._execute_speedtest()
        except Iperf3Timeout as exc:
            self._ensure_connectivity_after_timeout()
            print(
                "[collector] iPerf3 measurement exceeded its wall-clock timeout; "
                f"discarding attempt and starting a fresh first attempt: {exc}",
                flush=True,
            )
            try:
                return self._execute_speedtest()
            except Iperf3Timeout:
                # Re-check after the retry too, because the link may have gone
                # down during the second attempt.
                self._ensure_connectivity_after_timeout()
                raise

    def _ensure_connectivity_after_timeout(self) -> None:
        """Avoid misclassifying an internet outage as a measurement failure."""
        snapshot = probe_connectivity()
        if not snapshot.gateway_reachable:
            raise ConnectivityFailure(
                "gateway_unreachable",
                "INTERNAL",
                snapshot,
                "gateway indisponível após timeout do iPerf3",
                "high",
            )
        if not snapshot.external_reachable:
            self._raise_external_failure(snapshot, "external_timeout")

    def _save_external_failure(
        self,
        slot: dict,
        snapshot: ConnectivitySnapshot,
        cause: str,
    ) -> Sample:
        count = self._next_external_failure_count()
        origin, confidence = self._external_failure_classification(count)
        return self._save_failure(
            slot,
            cause=cause,
            origin=origin,
            snapshot=snapshot,
            note=(
                f"falha externa consecutiva {count}/3; "
                f"gateway={snapshot.gateway_reachable}, "
                f"externa={snapshot.external_reachable}"
            ),
            classification_confidence=confidence,
        )

    def _raise_external_failure(
        self,
        snapshot: ConnectivitySnapshot,
        cause: str,
    ) -> None:
        count = self._next_external_failure_count()
        origin, confidence = self._external_failure_classification(count)
        raise ConnectivityFailure(
            cause,
            origin,
            snapshot,
            (
                f"falha externa consecutiva {count}/3 após timeout do iPerf3; "
                f"gateway={snapshot.gateway_reachable}, "
                f"externa={snapshot.external_reachable}"
            ),
            confidence,
        )

    def _next_external_failure_count(self) -> int:
        count_method = getattr(self.store, "consecutive_external_failure_count", None)
        previous = count_method(self.settings.speedtest_runner) if count_method else 0
        return previous + 1

    @staticmethod
    def _external_failure_classification(count: int) -> tuple[str, str]:
        if count >= 3:
            return "OPERATOR", "high"
        return "UNKNOWN", "low"

    def _save_measurement_failure(
        self,
        slot: dict,
        connectivity: ConnectivitySnapshot,
        exc: Exception,
    ) -> Sample:
        cause = self._classify_failure(exc)
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(
            f"[collector] {started_at} FAILURE cause={cause}: {exc}",
            flush=True,
        )
        return self._save_failure(
            slot,
            cause=cause,
            origin="MEASUREMENT",
            note=str(exc)[:400],
            snapshot=connectivity,
        )

    def _save_failure(
        self,
        slot: dict,
        cause: str,
        origin: str,
        snapshot: ConnectivitySnapshot,
        note: Optional[str] = None,
        classification_confidence: Optional[str] = None,
    ) -> Sample:
        started_at = self._attempt_started_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        failure_note = note or json.dumps(snapshot.evidence, sort_keys=True)
        sample = Sample(
            started_at=started_at,
            is_failure=True,
            failure_cause=cause,
            failure_note=failure_note[:400],
            slot_id=slot["id"],
            local_date=slot["local_date"],
            quadrant=slot["quadrant"],
            failure_origin=origin,
            runner=self.settings.speedtest_runner,
            power_state="UNKNOWN",
            gateway_reachable=snapshot.gateway_reachable,
            external_reachable=snapshot.external_reachable,
            classification_confidence=(
                classification_confidence
                or ("medium" if origin != "MEASUREMENT" else "high")
            ),
            evidence_json=json.dumps(snapshot.evidence, sort_keys=True),
        )
        sample_id = self.store.add_sample(sample)
        self._evaluate_alerts(sample, sample_id)
        print(
            f"[collector] {started_at} FAILURE cause={cause} origin={origin} "
            f"quadrant={slot['quadrant']}",
            flush=True,
        )
        return sample

    def _heartbeat(
        self,
        status: str,
        metadata: Optional[dict] = None,
        force: bool = False,
    ) -> None:
        """Publish collector liveness without turning the DB into a log."""
        record = getattr(self.store, "record_heartbeat", None)
        if record is None:
            return
        now = time.monotonic()
        if not force and now - self._last_heartbeat_monotonic < 30:
            return
        try:
            record("collector", status, metadata or {})
            self._last_heartbeat_monotonic = now
        except Exception as exc:  # pragma: no cover - defensive operational path
            print(f"[collector] heartbeat unavailable: {exc}", flush=True)

    def _evaluate_alerts(self, sample: Sample, sample_id: Optional[int]) -> None:
        """Persist actionable alerts and optionally deliver them to a webhook."""
        add_alert = getattr(self.store, "add_alert", None)
        if add_alert is None:
            return
        kind = None
        severity = "warning"
        message = ""
        if sample.is_failure and sample.failure_origin == "OPERATOR":
            kind = "operator_outage"
            severity = "critical"
            message = "Três falhas externas consecutivas indicam provável indisponibilidade da operadora."
        elif not sample.is_failure:
            contracted = sample.bandwidth_contracted_mbps
            if contracted and contracted > 0 and sample.download_mbps is not None:
                threshold = getattr(self.settings, "alert_speed_threshold_pct", 80.0)
                delivery = sample.download_mbps / contracted * 100
                if delivery < threshold:
                    kind = "speed_degraded"
                    message = (
                        f"Download abaixo do limite configurado: {sample.download_mbps:.2f} Mbps "
                        f"({delivery:.1f}% do contrato de {contracted:.2f} Mbps)."
                    )
        transition = getattr(self.store, 'transition_alert_state', None)
        if transition:
            if kind:
                transition(kind, True)
            if not sample.is_failure:
                for incident, resolved in (('operator_outage', True), ('speed_degraded', kind != 'speed_degraded')):
                    if resolved:
                        transition(incident, False, sample_id, {'started_at': sample.started_at})
        if not kind:
            return
        alert_id = add_alert(
            kind=kind,
            message=message,
            severity=severity,
            sample_id=sample_id if isinstance(sample_id, int) else None,
            payload={
                "started_at": sample.started_at,
                "runner": sample.runner,
                "slot_id": sample.slot_id,
                "quadrant": sample.quadrant,
                "download_mbps": sample.download_mbps,
                "failure_cause": sample.failure_cause,
            },
            cooldown_seconds=getattr(self.settings, "alert_cooldown_seconds", 21600),
        )
        if alert_id is None:
            return
        print(f"[collector] ALERT id={alert_id} kind={kind}: {message}", flush=True)

    def _classify_failure(self, exc: Exception) -> str:
        """Map a speedtest exception to a short, stable failure cause label."""
        text = f"{exc!r}".lower()
        for cause, needles in (
            ("timeout", ("timed out", "timeout", "timedout")),
            ("network", ("network", "connection", "socket", "refused", "reset", "unreachable")),
            ("dns", ("dns", "name resolution", "getaddrinfo", "name or service")),
            ("server", ("server", "no servers", "cannot connect")),
            ("upload", ("upload",)),
            ("download", ("download",)),
        ):
            if any(n in text for n in needles):
                return cause
        return "unknown"

    def _ensure_schedule(self, local_day: date) -> None:
        planned = plan_day_slots(
            local_day=local_day,
            tz_name=self.settings.timezone,
            count_per_quadrant=self.settings.measurements_per_quadrant,
            test_duration_seconds=self.settings.sample_duration_seconds,
        )
        self.store.add_slots(
            MeasurementSlot(
                local_date=slot.local_date,
                quadrant=slot.quadrant,
                slot_index=slot.slot_index,
                scheduled_for=slot.scheduled_for,
                schedule_seed=slot.schedule_seed,
            )
            for slot in planned
        )

    def run_forever(self) -> None:
        """Maintain the daily plan and process due slots until stopped."""
        print(
            f"[collector] starting: {self.settings.measurements_per_quadrant} "
            "measurement(s) per quadrant, "
            f"duration={self.settings.sample_duration_seconds}s, "
            f"runner={self.settings.speedtest_runner}, "
            f"timeout={getattr(self.settings, 'measurement_timeout_seconds', 60)}s",
            flush=True,
        )
        self._heartbeat(
            "starting",
            {"runner": self.settings.speedtest_runner},
            force=True,
        )
        start_observation(self.store, self.settings)
        dispatcher_stop = Event()
        def dispatch_alerts():
            try:
                while not dispatcher_stop.is_set():
                    try:
                        deliver_due(self.store, self.settings.alert_webhook_url)
                    except Exception as exc:
                        print(f"[collector] alert dispatcher unavailable: {type(exc).__name__}", flush=True)
                    dispatcher_stop.wait(5)
            finally:
                self.store.close()
        dispatcher = Thread(target=dispatch_alerts, daemon=True)
        dispatcher.start()
        while not self._stop:
            now = datetime.now(timezone.utc)
            today = local_date_now(self.settings.timezone, now)
            self._ensure_schedule(today)
            self._ensure_schedule(today + timedelta(days=1))

            self.store.recover_stale_slots(now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                lease_seconds=getattr(self.settings, "slot_lease_seconds", 300),
                late_tolerance_seconds=self.settings.scheduler_late_tolerance_seconds)

            cutoff = now - timedelta(
                seconds=self.settings.scheduler_late_tolerance_seconds
            )
            self.store.mark_overdue_slots(
                cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            due = self.store.due_slots(now.strftime("%Y-%m-%dT%H:%M:%SZ"))
            if due:
                for slot in due:
                    if self._stop:
                        break
                    if not self.store.claim_slot(slot["id"]):
                        continue
                    self._heartbeat(
                        "measuring",
                        {"runner": self.settings.speedtest_runner, "slot_id": slot["id"]},
                        force=True,
                    )
                    with self._keep_measurement_alive(slot["id"]):
                        sample = self._run_single(slot)
                    # add_sample commits the representative row and terminal
                    # slot state in one transaction, including failure results.
                    self._heartbeat(
                        "idle",
                        {
                            "runner": self.settings.speedtest_runner,
                            "last_slot_id": slot["id"],
                            "last_measurement_at": sample.started_at if sample else None,
                        },
                        force=True,
                    )
                continue

            # Poll frequently enough to start a slot close to its planned time.
            self._heartbeat("idle", {"runner": self.settings.speedtest_runner})
            time.sleep(5)
        dispatcher_stop.set()
        dispatcher.join(timeout=6)
        self._heartbeat("stopped", {"runner": self.settings.speedtest_runner}, force=True)

    @contextmanager
    def _keep_measurement_alive(self, slot_id: int):
        """Renew execution leases and heartbeat while blocking runners are active."""
        stopped = Event()
        def renew():
            try:
                while not stopped.wait(20):
                    try:
                        self.store.touch_slot(slot_id)
                        self._heartbeat("measuring", {"slot_id": slot_id}, force=True)
                    except Exception as exc:
                        print(f"[collector] lease renewal unavailable: {exc}", flush=True)
            finally:
                self.store.close()
        worker = Thread(target=renew, daemon=True)
        worker.start()
        try:
            yield
        finally:
            stopped.set()
            worker.join(timeout=10)

    @staticmethod
    def _slot_status_for_sample(sample: Optional[Sample]) -> str:
        if not sample or not sample.is_failure:
            return "SUCCESS"
        if sample.failure_cause == "power":
            return "POWER_OUTAGE"
        if sample.failure_origin == "OPERATOR":
            return "NO_INTERNET_OPERATOR"
        if sample.failure_origin == "INTERNAL":
            return "NO_INTERNET_INTERNAL"
        return "MEASUREMENT_ERROR"


def main() -> int:
    """Load environment configuration and run the collector process."""
    settings = load_settings()
    store = SampleStore(settings.db_path)
    collector = Collector(settings, store)

    signal.signal(signal.SIGINT, collector._handle_signal)
    signal.signal(signal.SIGTERM, collector._handle_signal)

    try:
        collector.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
