# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Rules for deciding whether a speedtest result needs one immediate retry."""
from __future__ import annotations

from typing import Optional


def anomalous_directions(
    download_mbps: float,
    upload_mbps: float,
    contracted_download_mbps: Optional[float],
    contracted_upload_mbps: Optional[float],
    retry_ratio: Optional[float],
    absolute_min_download_mbps: Optional[float] = None,
) -> list[str]:
    """List directions below configured thresholds; never infer an unknown plan.

    The collector retries the complete pair only once if either direction is
    anomalous. Equality at the threshold is not anomalous. The existing absolute
    threshold remains download-only for backwards compatibility.
    """
    directions = []
    if is_anomalous_download(download_mbps, contracted_download_mbps, retry_ratio, absolute_min_download_mbps):
        directions.append("download")
    if is_anomalous_download(upload_mbps, contracted_upload_mbps, retry_ratio, None):
        directions.append("upload")
    return directions


def is_anomalous_download(
    download_mbps: float,
    contracted_mbps: Optional[float],
    retry_ratio: Optional[float],
    absolute_min_mbps: Optional[float],
) -> bool:
    """Return whether the first download result should be discarded and retried.

    The relative threshold is based on the contracted download speed. An
    optional absolute threshold is useful when no contract value is available.
    Either configured threshold can trigger the retry. Non-positive thresholds
    are ignored so a bad environment value cannot make every result anomalous.
    """
    thresholds: list[float] = []
    if contracted_mbps is not None and contracted_mbps > 0:
        if retry_ratio is not None and retry_ratio > 0:
            thresholds.append(contracted_mbps * retry_ratio)
    if absolute_min_mbps is not None and absolute_min_mbps > 0:
        thresholds.append(absolute_min_mbps)
    return bool(thresholds) and download_mbps < max(thresholds)
