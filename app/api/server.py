# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""SpeedTester API (FastAPI).

Endpoints:
    GET  /                      -> dashboard (HTML)
    GET /health                 -> liveness probe
    GET /api/samples            -> raw samples (optional filters: since, minutes)
    GET /api/summary            -> summary of stored data + latest sample
    GET /api/chart.png          -> chart of the day (download + upload over time)
    POST /api/reset             -> wipe all samples

The chart is generated on the fly with matplotlib and returned as PNG.
"""
from __future__ import annotations

import base64
import hmac
import io
import os
import time
from collections import defaultdict, deque
from threading import Lock
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # headless backend
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from fastapi import Body, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from api.store import SampleStore
from collector.quadrants import local_date_now
from shared.settings import Settings, load_settings

settings = load_settings()
store = SampleStore(settings.db_path)

app = FastAPI(title="SpeedTester", version="1.0.0")
_rate_limit_lock = Lock()
_rate_limit_buckets: dict[str, deque[float]] = defaultdict(deque)

# Serve the static dashboard HTML at /dashboard/index.html
_DASHBOARD_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard", "index.html")

_DASHBOARD_DIR = os.path.dirname(_DASHBOARD_HTML_PATH)
try:
    app.mount("/dashboard", StaticFiles(html=True, directory=_DASHBOARD_DIR), name="dashboard")
except Exception:  # pragma: no cover - defensive
    pass


@app.middleware("http")
async def api_rate_limit(request: Request, call_next):
    """Bound unauthenticated API abuse in this single-process service."""
    if request.url.path.startswith("/api/"):
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        with _rate_limit_lock:
            # Do not let a large number of short-lived client addresses turn
            # the in-memory limiter into an unbounded allocation.
            if client not in _rate_limit_buckets and len(_rate_limit_buckets) >= 10_000:
                stale_clients = [
                    key
                    for key, client_bucket in _rate_limit_buckets.items()
                    if not client_bucket or now - client_bucket[-1] >= 60
                ]
                for stale_client in stale_clients:
                    _rate_limit_buckets.pop(stale_client, None)
            bucket = _rate_limit_buckets[client]
            while bucket and now - bucket[0] >= 60:
                bucket.popleft()
            limit = max(1, settings.api_rate_limit_per_minute)
            if len(bucket) >= limit:
                return JSONResponse(
                    {"detail": "rate limit exceeded"},
                    status_code=429,
                    headers={"Retry-After": "60"},
                )
            bucket.append(now)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    return response


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collector_health() -> dict:
    heartbeat = store.latest_heartbeat("collector")
    if not heartbeat:
        return {
            "status": "unknown",
            "observed_at": None,
            "age_seconds": None,
            "metadata": {},
        }
    try:
        observed = datetime.fromisoformat(heartbeat["observed_at"].replace("Z", "+00:00"))
        age_seconds = max(0.0, (datetime.now(timezone.utc) - observed).total_seconds())
    except (KeyError, ValueError):
        age_seconds = None
    timeout = getattr(settings, "collector_heartbeat_timeout_seconds", 120)
    status = heartbeat.get("status", "unknown")
    if age_seconds is None or age_seconds > timeout or status == "stopped":
        status = "stale"
    elif status not in {"starting", "measuring", "idle", "ok"}:
        status = "unknown"
    return {
        "status": "ok" if status in {"starting", "measuring", "idle", "ok"} else status,
        "observed_at": heartbeat.get("observed_at"),
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "metadata": heartbeat.get("metadata", {}),
    }


# --- routes ----------------------------------------------------------------
@app.get("/health")
def health():
    """Return API liveness, persisted row count and collector heartbeat."""
    collector = _collector_health()
    return {
        "status": "ok" if collector["status"] == "ok" else "degraded",
        "rows": store.count(),
        "ts": _utcnow_iso(),
        "collector": collector,
    }


@app.get("/api/alerts")
def api_alerts(limit: int = Query(50, ge=1, le=200)):
    """Return the newest persisted alerts, capped by ``limit``."""
    return JSONResponse(store.alerts(limit))


@app.get("/api/samples")
def api_samples(
    since: Optional[str] = Query(None, description="ISO-8601 UTC cutoff, inclusive"),
    minutes: Optional[int] = Query(None, description="Only the last N minutes"),
    runner: Optional[str] = Query(None, description="Filter by fast, ookla or iperf3"),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Return paginated samples, optionally filtered by time window and runner."""
    if minutes is not None:
        rows = store.samples_last_minutes(minutes, limit=limit, offset=offset)
    elif since is not None:
        rows = store.samples_since(since, limit=limit, offset=offset)
    else:
        rows = store.all_samples(limit=limit, offset=offset)
    return JSONResponse(_filter_rows_for_runner(rows, runner))


@app.get("/api/slots")
def api_slots(local_date: Optional[str] = Query(None, alias="date")):
    """Return the persisted measurement plan for one local calendar day."""
    if local_date is None:
        local_date = local_date_now(settings.timezone).isoformat()
    return JSONResponse(store.slots_for_date(local_date))


@app.post("/api/slots/{slot_id}/classify")
def classify_slot(
    slot_id: int,
    payload: dict = Body(...),
    admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    """Manually correct an unresolved slot while preserving the note."""
    _require_admin_token(admin_token)
    status = str(payload.get("status", ""))
    allowed = {
        "POWER_OUTAGE",
        "NO_INTERNET_OPERATOR",
        "NO_INTERNET_INTERNAL",
        "MEASUREMENT_ERROR",
        "MISSED_UNKNOWN",
        "CANCELLED",
    }
    if status not in allowed:
        raise HTTPException(status_code=422, detail="invalid manual slot status")
    note = str(payload.get("note", "")).strip()
    if not note:
        raise HTTPException(status_code=422, detail="note is required")
    if not store.classify_slot(slot_id, status, note):
        raise HTTPException(status_code=404, detail="slot not found")
    return {"id": slot_id, "status": status, "source": "manual"}


@app.get("/api/availability-events")
def api_availability_events():
    """Return manually or externally registered availability intervals."""
    return JSONResponse(store.availability_events())


@app.post("/api/availability-events")
def create_availability_event(
    payload: dict = Body(...),
    admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    """Register an outage interval and reconcile affected pending slots."""
    _require_admin_token(admin_token)
    required = ("started_at", "event_type", "source")
    missing = [name for name in required if not payload.get(name)]
    if missing:
        raise HTTPException(status_code=422, detail=f"missing fields: {missing}")
    event_type = str(payload["event_type"])
    if event_type not in {"POWER_OUTAGE", "OPERATOR_OUTAGE", "INTERNAL_OUTAGE", "UNKNOWN"}:
        raise HTTPException(status_code=422, detail="invalid event_type")
    source = str(payload["source"])
    if event_type == "POWER_OUTAGE" and source != "manual":
        raise HTTPException(
            status_code=422,
            detail="POWER_OUTAGE must currently be registered with source=manual",
        )
    ended_at = payload.get("ended_at")
    if ended_at and str(ended_at) < str(payload["started_at"]):
        raise HTTPException(status_code=422, detail="ended_at must not precede started_at")
    event_id = store.add_availability_event(
        started_at=str(payload["started_at"]),
        ended_at=str(ended_at) if ended_at else None,
        event_type=event_type,
        source=source,
        confidence=str(payload.get("confidence", "medium")),
        note=str(payload["note"])[:400] if payload.get("note") else None,
    )
    return {"id": event_id, "event_type": event_type}


@app.get("/api/summary")
def api_summary(
    local_date: Optional[str] = Query(None, alias="date"),
    runner: Optional[str] = Query(None, description="Filter the main statistics by runner"),
):
    """Return aggregate speed, quality, failure, downtime and coverage metrics."""
    all_rows = _filter_rows_for_date(store.all_samples(), local_date)
    by_runner_rows = _compute_runner_metrics(all_rows)
    all_rows = _filter_rows_for_runner(all_rows, runner)
    slots = store.slots_for_date(local_date) if local_date else store.all_slots()
    events = _filter_events_for_date(store.availability_events(), local_date)
    coverage = _compute_coverage(slots)
    downtime = _compute_downtime(events)
    if not all_rows:
        return {
            "count": 0,
            "first": None,
            "last": None,
            "latest": None,
            "download_avg_mbps": None,
            "upload_avg_mbps": None,
            "download_max_mbps": None,
            "upload_max_mbps": None,
            "ping_avg_ms": None,
            "jitter_avg_ms": None,
            "packet_loss_avg_pct": None,
            "tcp_retransmits_avg": None,
            "latest_isp": None,
            "bandwidth_contracted_mbps": None,
            "failure_count": 0,
            "failure_rate_pct": None,
            "downtime": downtime,
            "outliers": {"download": [], "upload": []},
            "coverage": coverage,
            "quadrants": _empty_quadrant_metrics(),
            "runner": runner,
            "by_runner": by_runner_rows,
        }
    df = pd.DataFrame(all_rows)
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)
    df = df.sort_values("started_at").reset_index(drop=True)
    first = df["started_at"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ")
    last = df["started_at"].iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ")
    latest = all_rows[-1]

    # --- mean speeds (only over successful samples) --------------------------
    # Filter successful samples. Use boolean mask via .loc: is_failure is an
    # integer column, so df[mask] (where mask is an int Series) no longer means
    # positional indexing in pandas >= 3.0 and raises KeyError.
    good = df.loc[df["is_failure"] == 0]
    download_avg = round(float(good["download_mbps"].mean()), 2) if len(good) else None
    upload_avg = round(float(good["upload_mbps"].mean()), 2) if len(good) else None
    download_max = round(float(good["download_mbps"].max()), 2) if len(good) else None
    upload_max = round(float(good["upload_mbps"].max()), 2) if len(good) else None
    ping_avg = _metric_average(good, "ping_ms")
    jitter_avg = _metric_average(good, "jitter_ms")
    packet_loss_avg = _metric_average(good, "packet_loss_pct")
    retransmits_avg = _metric_average(good, "tcp_retransmits")

    # --- failure rate --------------------------------------------------------
    failure_rows = df[df["is_failure"] == 1]
    failure_count = int(len(failure_rows))
    failure_rate = round(100.0 * failure_count / len(df), 2)

    # --- downtime from explicitly registered availability events -------------
    # Gaps between samples are not downtime: the collector may simply be off.
    quadrants = _compute_quadrant_metrics(df)

    # --- outliers (Tukey fence on successful samples) ------------------------
    outliers = _compute_outliers(good)

    # Latest ISP and contracted-bandwidth (may be NULL on older / failed rows).
    latest_isp = latest.get("isp")
    latest_contracted = latest.get("bandwidth_contracted_mbps")

    summary = {
        "count": len(all_rows),
        "first": first,
        "last": last,
        "latest": latest,
        "latest_isp": latest_isp,
        "bandwidth_contracted_mbps": latest_contracted,
        "download_avg_mbps": download_avg,
        "upload_avg_mbps": upload_avg,
        "download_max_mbps": download_max,
        "upload_max_mbps": upload_max,
        "ping_avg_ms": ping_avg,
        "jitter_avg_ms": jitter_avg,
        "packet_loss_avg_pct": packet_loss_avg,
        "tcp_retransmits_avg": retransmits_avg,
        "failure_count": failure_count,
        "failure_rate_pct": failure_rate,
        "downtime": downtime,
        "outliers": outliers,
        "coverage": coverage,
        "quadrants": quadrants,
        "runner": runner,
        "by_runner": by_runner_rows,
    }
    return summary


@app.get("/api/comparison")
def api_comparison(
    from_date: str = Query(..., alias="from", description="First local date"),
    to_date: str = Query(..., alias="to", description="Last local date"),
    runner: Optional[str] = Query(None, description="Filter by runner"),
):
    """Return daily speed, delivery, failures and coverage for a date range."""
    try:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="from/to must be YYYY-MM-DD") from exc
    if end < start:
        raise HTTPException(status_code=422, detail="to must not precede from")
    if (end - start).days > 366:
        raise HTTPException(status_code=422, detail="comparison range is limited to 366 days")
    rows = _filter_rows_for_runner(store.all_samples(), runner)
    rows_by_day: dict[str, list[dict]] = {}
    for row in rows:
        row_day = row.get("local_date")
        if not row_day:
            timestamp = pd.to_datetime(row.get("started_at"), utc=True)
            row_day = timestamp.tz_convert(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d")
        if from_date <= row_day <= to_date:
            rows_by_day.setdefault(row_day, []).append(row)
    slots = store.all_slots()
    slots_by_day: dict[str, list[dict]] = {}
    for slot in slots:
        if from_date <= slot.get("local_date", "") <= to_date:
            slots_by_day.setdefault(slot["local_date"], []).append(slot)
    days = []
    current = start
    while current <= end:
        day_key = current.isoformat()
        day_rows = rows_by_day.get(day_key, [])
        good = [row for row in day_rows if not row.get("is_failure")]
        downloads = [float(row["download_mbps"]) for row in good if row.get("download_mbps") is not None]
        uploads = [float(row["upload_mbps"]) for row in good if row.get("upload_mbps") is not None]
        contracted_values = [
            float(row["bandwidth_contracted_mbps"])
            for row in day_rows
            if row.get("bandwidth_contracted_mbps") is not None
        ]
        contracted = contracted_values[-1] if contracted_values else settings.bandwidth_contracted_mbps
        download_avg = sum(downloads) / len(downloads) if downloads else None
        coverage = _compute_coverage(slots_by_day.get(day_key, []))
        days.append(
            {
                "date": day_key,
                "samples": len(day_rows),
                "success_count": len(good),
                "failure_count": len(day_rows) - len(good),
                "failure_rate_pct": round(100 * (len(day_rows) - len(good)) / len(day_rows), 2) if day_rows else None,
                "download_avg_mbps": round(download_avg, 2) if download_avg is not None else None,
                "upload_avg_mbps": round(sum(uploads) / len(uploads), 2) if uploads else None,
                "contracted_mbps": contracted,
                "delivery_pct": round(100 * download_avg / contracted, 2) if download_avg is not None and contracted else None,
                "coverage_pct": coverage["coverage_pct"],
                "coverage": coverage,
            }
        )
        current += timedelta(days=1)
    return {"from": from_date, "to": to_date, "runner": runner, "days": days}


@app.post("/api/reset")
async def api_reset(admin_token: Optional[str] = Header(None, alias="X-Admin-Token")):
    """Delete measurement history after validating the administrative token."""
    _require_admin_token(admin_token)
    n = store.reset()
    return {"reset_rows": n}


@app.get("/api/chart.png")
def api_chart(
    local_date: Optional[str] = Query(None, alias="date"),
    runner: Optional[str] = Query(None, description="Filter chart by runner"),
):
    """Return a PNG chart of download & upload speeds over the last 24h."""
    rows = _filter_rows_for_runner(
        _filter_rows_for_date(store.all_samples(), local_date), runner
    )
    fig = _build_chart(rows)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    data = buf.read()
    return Response(content=data, media_type="image/png")


def _build_chart(rows: list):
    if not rows:
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.text(0.5, 0.5, "No data yet", ha="center", va="center", fontsize=14)
        ax.set_axis_off()
        return fig

    df = pd.DataFrame(rows)
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)
    df = df.sort_values("started_at").reset_index(drop=True)

    # Focus on the last 24h if there is more than a day of data.
    span_min = (df["started_at"].iloc[-1] - df["started_at"].iloc[0]).total_seconds() / 60
    if span_min > 24 * 60:
        cutoff = df["started_at"].iloc[-1] - pd.Timedelta(hours=24)
        df = df[df["started_at"] >= cutoff]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(df["started_at"], df["download_mbps"], marker="o", label="Download", color="#1f77b4", linewidth=2)
    ax.plot(df["started_at"], df["upload_mbps"], marker="s", label="Upload", color="#ff7f0e", linewidth=2)
    ax.set_ylabel("Mbps")
    contracted = df["bandwidth_contracted_mbps"].dropna()
    if len(contracted):
        ax.axhline(
            float(contracted.iloc[-1]),
            color="#35c46b",
            linestyle="--",
            linewidth=1.8,
            label=f"Contrato ({float(contracted.iloc[-1]):g} Mbps)",
        )
    ax.set_xlabel(f"Hora ({settings.timezone})")
    ax.set_title("SpeedTester — download/upload versus contrato")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(
        mdates.DateFormatter("%H:%M", tz=ZoneInfo(settings.timezone))
    )
    fig.autofmt_xdate()
    return fig


# --- analytics helpers ------------------------------------------------------
def _require_admin_token(token: Optional[str]) -> None:
    """Enforce the configured token when the API is deployed remotely."""
    if not settings.api_admin_token:
        if settings.api_require_admin_token:
            raise HTTPException(status_code=503, detail="admin token is not configured")
        return
    if not token or not hmac.compare_digest(token, settings.api_admin_token):
        raise HTTPException(status_code=403, detail="invalid admin token")


def _filter_rows_for_date(rows: list[dict], local_date: Optional[str]) -> list[dict]:
    if not local_date:
        return rows
    try:
        date.fromisoformat(local_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    filtered = []
    for row in rows:
        if row.get("local_date") == local_date:
            filtered.append(row)
            continue
        timestamp = pd.to_datetime(row.get("started_at"), utc=True)
        if timestamp.tz_convert(ZoneInfo(settings.timezone)).strftime("%Y-%m-%d") == local_date:
            filtered.append(row)
    return filtered


def _filter_rows_for_runner(rows: list[dict], runner: Optional[str]) -> list[dict]:
    """Filter samples without treating legacy NULL runners as a real runner."""
    if not runner:
        return rows
    normalized = runner.strip().lower()
    if normalized not in {"fast", "ookla", "iperf3"}:
        raise HTTPException(status_code=422, detail="runner must be fast, ookla or iperf3")
    return [row for row in rows if (row.get("runner") or "").lower() == normalized]


def _filter_events_for_date(events: list[dict], local_date: Optional[str]) -> list[dict]:
    if not local_date:
        return events
    try:
        selected = date.fromisoformat(local_date)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    zone = ZoneInfo(settings.timezone)
    start = pd.Timestamp(datetime.combine(selected, datetime.min.time(), tzinfo=zone)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(selected + timedelta(days=1), datetime.min.time(), tzinfo=zone)).tz_convert("UTC")
    result = []
    for event in events:
        event_start = pd.to_datetime(event["started_at"], utc=True)
        event_end = pd.to_datetime(event["ended_at"], utc=True) if event.get("ended_at") else pd.Timestamp.now(tz="UTC")
        if event_start < end and event_end >= start:
            result.append(event)
    return result


def _empty_quadrant_metrics() -> dict:
    return {
        name: {
            "count": 0,
            "download_avg_mbps": None,
            "upload_avg_mbps": None,
            "download_median_mbps": None,
            "upload_median_mbps": None,
            "ping_avg_ms": None,
            "jitter_avg_ms": None,
            "packet_loss_avg_pct": None,
        }
        for name in ("madrugada", "manha", "tarde", "noite")
    }


def _compute_runner_metrics(rows: list[dict]) -> dict:
    """Compute independent statistics for each persisted runner."""
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    df["started_at"] = pd.to_datetime(df["started_at"], utc=True)
    result = {}
    for runner, group in df.groupby(df["runner"].fillna("legacy"), sort=True):
        good = group.loc[group["is_failure"] == 0]
        result[str(runner)] = {
            "count": int(len(group)),
            "success_count": int(len(good)),
            "failure_count": int((group["is_failure"] == 1).sum()),
            "download_avg_mbps": _metric_average(good, "download_mbps"),
            "download_median_mbps": _metric_median(good, "download_mbps"),
            "download_max_mbps": _metric_max(good, "download_mbps"),
            "upload_avg_mbps": _metric_average(good, "upload_mbps"),
            "upload_median_mbps": _metric_median(good, "upload_mbps"),
            "upload_max_mbps": _metric_max(good, "upload_mbps"),
            "ping_avg_ms": _metric_average(good, "ping_ms"),
            "jitter_avg_ms": _metric_average(good, "jitter_ms"),
            "packet_loss_avg_pct": _metric_average(good, "packet_loss_pct"),
            "tcp_retransmits_avg": _metric_average(good, "tcp_retransmits"),
        }
    return result


def _compute_quadrant_metrics(df: pd.DataFrame) -> dict:
    metrics = _empty_quadrant_metrics()
    if "quadrant" not in df.columns:
        return metrics
    for name in metrics:
        group = df.loc[(df["quadrant"] == name) & (df["is_failure"] == 0)]
        if group.empty:
            continue
        metrics[name] = {
            "count": int(len(group)),
            "download_avg_mbps": round(float(group["download_mbps"].mean()), 2),
            "upload_avg_mbps": round(float(group["upload_mbps"].mean()), 2),
            "download_median_mbps": round(float(group["download_mbps"].median()), 2),
            "upload_median_mbps": round(float(group["upload_mbps"].median()), 2),
            "ping_avg_ms": _metric_average(group, "ping_ms"),
            "jitter_avg_ms": _metric_average(group, "jitter_ms"),
            "packet_loss_avg_pct": _metric_average(group, "packet_loss_pct"),
        }
    return metrics


def _metric_average(df: pd.DataFrame, name: str) -> Optional[float]:
    """Average an optional metric without failing on legacy databases."""
    if name not in df.columns:
        return None
    values = pd.to_numeric(df[name], errors="coerce").dropna()
    # Ignore impossible legacy readings (older fast.com timeout samples could
    # persist elapsed-time values as latency) without deleting raw evidence.
    if name in {"ping_ms", "jitter_ms", "latency_min_ms", "latency_max_ms"}:
        values = values[(values >= 0) & (values <= 5_000)]
    elif name == "packet_loss_pct":
        values = values[(values >= 0) & (values <= 100)]
    elif name == "tcp_retransmits":
        values = values[values >= 0]
    return round(float(values.mean()), 2) if len(values) else None


def _metric_median(df: pd.DataFrame, name: str) -> Optional[float]:
    if name not in df.columns:
        return None
    values = pd.to_numeric(df[name], errors="coerce").dropna()
    return round(float(values.median()), 2) if len(values) else None


def _metric_max(df: pd.DataFrame, name: str) -> Optional[float]:
    if name not in df.columns:
        return None
    values = pd.to_numeric(df[name], errors="coerce").dropna()
    return round(float(values.max()), 2) if len(values) else None


def _compute_coverage(slots: list[dict]) -> dict:
    """Summarize expected, completed and classified slots."""
    quadrants = {name: {"expected": 0, "completed": 0, "statuses": {}} for name in ("madrugada", "manha", "tarde", "noite")}
    statuses: dict[str, int] = {}
    completed = 0
    for slot in slots:
        status = slot.get("status", "PENDING")
        quadrant = slot.get("quadrant")
        if quadrant not in quadrants:
            continue
        quadrants[quadrant]["expected"] += 1
        statuses[status] = statuses.get(status, 0) + 1
        quadrants[quadrant]["statuses"][status] = quadrants[quadrant]["statuses"].get(status, 0) + 1
        if status == "SUCCESS":
            completed += 1
            quadrants[quadrant]["completed"] += 1
    expected = len(slots)
    return {
        "expected": expected,
        "completed": completed,
        "missing": expected - completed,
        "coverage_pct": round(100.0 * completed / expected, 2) if expected else None,
        "statuses": statuses,
        "by_quadrant": quadrants,
    }


def _compute_downtime(events: list[dict]) -> dict:
    """Calculate downtime from registered events, merging total overlaps."""
    now = pd.Timestamp.now(tz="UTC")
    intervals: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    by_origin: dict[str, float] = {}
    for event in events:
        start = pd.to_datetime(event["started_at"], utc=True)
        end = pd.to_datetime(event["ended_at"], utc=True) if event.get("ended_at") else now
        if end <= start:
            continue
        intervals.append((start, end))
        origin = str(event.get("event_type", "UNKNOWN"))
        by_origin[origin] = by_origin.get(origin, 0.0) + (end - start).total_seconds() / 60.0

    intervals.sort(key=lambda item: item[0])
    merged: list[list[pd.Timestamp]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total_minutes = sum((end - start).total_seconds() / 60.0 for start, end in merged)

    years = int(total_minutes // (365.25 * 24 * 60))
    remainder = total_minutes - years * 365.25 * 24 * 60
    months = int(remainder // (30.44 * 24 * 60))
    remainder -= months * 30.44 * 24 * 60
    weeks = int(remainder // (7 * 24 * 60))
    remainder -= weeks * 7 * 24 * 60
    days = int(remainder // (24 * 60))
    remainder -= days * 24 * 60
    hours = int(remainder // 60)
    remainder -= hours * 60
    minutes = int(remainder)

    return {
        "total_minutes": round(total_minutes, 1),
        "years": years,
        "months": months,
        "weeks": weeks,
        "days": days,
        "hours": hours,
        "minutes": minutes,
        "by_origin_minutes": {
            origin: round(value, 1) for origin, value in by_origin.items()
        },
    }


def _compute_outliers(df: pd.DataFrame) -> dict:
    """Tukey-fence outliers for download/upload on successful samples.

    An outlier is a value beyond 1.5x the inter-quartile range (Q1 - 1.5*IQR or
    Q3 + 1.5*IQR). Each outlier is reported as ``{"i": idx, "value": v,
    "zscore": z}`` so the dashboard can highlight anomalous points.
    """
    def _series(name: str) -> list:
        if name not in df.columns:
            return []
        s = df[name].dropna()
        if len(s) < 4:
            return []
        q1 = float(s.quantile(0.25))
        q3 = float(s.quantile(0.75))
        iqr = q3 - q1
        if iqr <= 0:
            return []
        lo = q1 - 1.5 * iqr
        hi = q3 + 1.5 * iqr
        z = (s - s.mean()) / s.std(ddof=0)
        mask = (s < lo) | (s > hi)
        out = []
        for i, v in s[mask].items():
            out.append({"i": int(i), "value": round(float(v), 2), "zscore": round(float(z.iloc[i]), 2)})
        return out

    return {"download": _series("download_mbps"), "upload": _series("upload_mbps")}


# Serve the dashboard as the root page.
with open(_DASHBOARD_HTML_PATH, "r", encoding="utf-8") as _fh:
    _DASHBOARD_HTML = _fh.read()


@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the dashboard HTML document."""
    return _DASHBOARD_HTML
