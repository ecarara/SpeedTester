# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara

"""Build the privacy-preserving network geography used by the dashboard.

The project stores the public-network identity as a historical snapshot, but
does not expose public IP addresses in the map response.  Existing samples do
not necessarily have coordinates, so the response uses a small deterministic
centroid catalogue as a visual fallback.  A point is labelled with its
precision (city, country or unavailable) so the UI never presents an
approximation as an exact location.
"""
from __future__ import annotations

from collections import defaultdict
import unicodedata


# The catalogue intentionally covers the locations most commonly returned by
# the collector while retaining a country-level fallback for other samples.
# Coordinates are centroids for visualization, not an address lookup.
CITY_CENTROIDS = {
    ("BR", "brasilia"): (-15.7939, -47.8828),
    ("BR", "belo horizonte"): (-19.9167, -43.9345),
    ("BR", "campinas"): (-22.9099, -47.0626),
    ("BR", "curitiba"): (-25.4284, -49.2733),
    ("BR", "florianopolis"): (-27.5954, -48.5480),
    ("BR", "joinville"): (-26.3045, -48.8487),
    ("BR", "londrina"): (-23.3045, -51.1696),
    ("BR", "maringa"): (-23.4205, -51.9333),
    ("BR", "porto alegre"): (-30.0346, -51.2177),
    ("BR", "recife"): (-8.0476, -34.8770),
    ("BR", "rio de janeiro"): (-22.9068, -43.1729),
    ("BR", "salvador"): (-12.9777, -38.5016),
    ("BR", "sao paulo"): (-23.5505, -46.6333),
    ("AR", "buenos aires"): (-34.6037, -58.3816),
    ("CL", "santiago"): (-33.4489, -70.6693),
    ("CO", "bogota"): (4.7110, -74.0721),
    ("MX", "mexico city"): (19.4326, -99.1332),
    ("PT", "lisbon"): (38.7223, -9.1393),
    ("US", "new york"): (40.7128, -74.0060),
    ("US", "san francisco"): (37.7749, -122.4194),
}

COUNTRY_CENTROIDS = {
    "AR": (-38.4161, -63.6167), "AU": (-25.2744, 133.7751),
    "BR": (-10.0000, -55.0000), "CA": (56.1304, -106.3468),
    "CL": (-35.6751, -71.5430), "CN": (35.8617, 104.1954),
    "CO": (4.5709, -74.2973), "DE": (51.1657, 10.4515),
    "ES": (40.4637, -3.7492), "FR": (46.2276, 2.2137),
    "GB": (55.3781, -3.4360), "IN": (20.5937, 78.9629),
    "IT": (41.8719, 12.5674), "JP": (36.2048, 138.2529),
    "MX": (23.6345, -102.5528), "NL": (52.1326, 5.2913),
    "PT": (39.3999, -8.2245), "PY": (-23.4425, -58.4438),
    "RU": (61.5240, 105.3188), "US": (37.0902, -95.7129),
    "UY": (-32.5228, -55.7658), "ZA": (-30.5595, 22.9375),
}


def _key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in text if not unicodedata.combining(char)).casefold().strip()


def _coordinates(row: dict) -> tuple[float | None, float | None, str]:
    code = str(row.get("country_code") or "").upper()
    city = _key(row.get("city"))
    if (code, city) in CITY_CENTROIDS:
        latitude, longitude = CITY_CENTROIDS[(code, city)]
        return latitude, longitude, "city-centroid"
    if code in COUNTRY_CENTROIDS:
        latitude, longitude = COUNTRY_CENTROIDS[code]
        return latitude, longitude, "country-centroid"
    return None, None, "unavailable"


def _row_identity(row: dict) -> tuple[str, str, str, str]:
    operator = row.get("isp") or row.get("isp_organization") or "Operadora não identificada"
    country = row.get("country") or "País não identificado"
    city = row.get("city") or "Cidade não identificada"
    code = str(row.get("country_code") or "").upper()
    return str(operator), str(country), str(city), code


def _add_metric(group: dict, row: dict, field: str, total_field: str, count_field: str) -> None:
    value = row.get(field)
    if value is not None:
        group[total_field] += float(value)
        group[count_field] += 1


def _accumulate_row(group: dict, row: dict) -> None:
    group["samples"] += 1
    if row.get("is_failure"):
        group["failure_count"] += 1
    else:
        group["success_count"] += 1
        _add_metric(group, row, "download_mbps", "download_total", "download_count")
        _add_metric(group, row, "upload_mbps", "upload_total", "upload_count")
    started_at = row.get("started_at", "")
    if not group["latest_at"] or started_at > group["latest_at"]:
        group["latest_at"] = started_at


def _new_group(row: dict) -> dict:
    operator, country, city, code = _row_identity(row)
    return {
        "operator": operator, "organization": row.get("isp_organization"),
        "country": country, "country_code": code or None, "city": city,
        "samples": 0, "success_count": 0, "failure_count": 0,
        "download_total": 0.0, "download_count": 0,
        "upload_total": 0.0, "upload_count": 0, "latest_at": None,
    }


def _point(index: int, group: dict) -> dict:
    latitude, longitude, precision = _coordinates(group)
    return {
        "id": f"network-{index}", "operator": group["operator"],
        "organization": group.get("organization"), "city": group["city"],
        "country": group["country"], "country_code": group.get("country_code"),
        "latitude": latitude, "longitude": longitude,
        "coordinate_source": precision, "samples": group["samples"],
        "success_count": group["success_count"], "failure_count": group["failure_count"],
        "avg_download_mbps": round(group["download_total"] / group["download_count"], 2) if group["download_count"] else None,
        "avg_upload_mbps": round(group["upload_total"] / group["upload_count"], 2) if group["upload_count"] else None,
        "latest_at": group["latest_at"],
    }


def build_network_map(rows: list[dict]) -> dict:
    """Aggregate samples into operator/city/country points for the UI."""
    groups: dict[tuple[str, str, str, str], dict] = defaultdict(lambda: {
        "samples": 0, "success_count": 0, "failure_count": 0,
        "download_total": 0.0, "download_count": 0,
        "upload_total": 0.0, "upload_count": 0, "latest_at": None,
    })
    for row in rows:
        identity = _row_identity(row)
        group = groups[identity]
        if not group.get("operator"):
            groups[identity] = group = _new_group(row)
        _accumulate_row(group, row)

    points = [_point(index, group) for index, group in enumerate(groups.values(), start=1)]
    points.sort(key=lambda item: (-item["samples"], item["operator"], item["city"]))
    return {
        "points": points,
        "totals": {
            "samples": sum(point["samples"] for point in points),
            "operators": len({point["operator"] for point in points}),
            "cities": len({(point["city"], point["country"]) for point in points}),
            "countries": len({point["country"] for point in points}),
            "unmapped": sum(point["latitude"] is None for point in points),
        },
    }
