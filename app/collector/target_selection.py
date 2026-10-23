# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Choose one public iPerf3 destination by geography, or honor an explicit host.

The finite catalog contains published public test endpoints, not arbitrary
hosts discovered by scans. Coordinates are city centroids. Selection sends no
packets to candidates and never uses throughput to choose a favorable result.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import ipaddress
import math
import re
import unicodedata


CATALOG_REVISION = "2026-10-23"
CATALOG_SOURCE = "https://export.iperf3serverlist.net/listed_iperf3_servers.json"


class TargetSelectionError(RuntimeError):
    """Location/catalog configuration failed; this is not an ISP outage."""


@dataclass(frozen=True)
class Target:
    host: str
    port: int = 5201
    country_code: str = ""
    city: str = ""
    latitude: float | None = None
    longitude: float | None = None
    capacity_gbps: float = 0
    mode: str = "automatic"
    distance_km: float | None = None


# City centroids and endpoints published in CATALOG_SOURCE on CATALOG_REVISION.
# All entries support TCP upload and reverse/download. Advertised capacity is
# only a tie-breaker at the same geographic distance, not a speed guarantee.
TARGETS = (
    Target("138.199.4.1", 5201, "BR", "São Paulo", -23.5505, -46.6333, 20),
    Target("148.230.60.200", 30001, "BR", "São Paulo", -23.5505, -46.6333, 10),
    Target("79.127.209.1", 5201, "CL", "Santiago", -33.4489, -70.6693, 20),
    Target("speedtest.mtl2.ca.leaseweb.net", 5201, "CA", "Montreal", 45.5019, -73.5674, 10),
    Target("138.199.57.129", 5201, "CA", "Toronto", 43.6532, -79.3832, 20),
    Target("speedtest.dal13.us.leaseweb.net", 5201, "US", "Dallas", 32.7767, -96.7970, 10),
    Target("la.speedtest.clouvider.net", 5200, "US", "Los Angeles", 34.0522, -118.2437, 10),
    Target("speedtest.mia11.us.leaseweb.net", 5201, "US", "Miami", 25.7617, -80.1918, 10),
    Target("spd-uswb.hostkey.com", 5201, "US", "New York", 40.7128, -74.0060, 10),
    Target("speedtest.sfo12.us.leaseweb.net", 5201, "US", "San Francisco", 37.7749, -122.4194, 10),
    Target("speedtest.sea11.us.leaseweb.net", 5201, "US", "Seattle", 47.6062, -122.3321, 10),
    Target("109.61.94.65", 5201, "PT", "Lisbon", 38.7223, -9.1393, 20),
    Target("185.93.3.50", 5201, "ES", "Madrid", 40.4168, -3.7038, 20),
    Target("185.93.2.193", 5201, "FR", "Paris", 48.8566, 2.3522, 20),
    Target("speedtest.lon1.uk.leaseweb.net", 5202, "GB", "London", 51.5074, -0.1278, 10),
    Target("speedtest.ams1.nl.leaseweb.net", 5201, "NL", "Amsterdam", 52.3676, 4.9041, 10),
    Target("fra.speedtest.clouvider.net", 5200, "DE", "Frankfurt", 50.1109, 8.6821, 10),
    Target("speedtest.sin1.sg.leaseweb.net", 5201, "SG", "Singapore", 1.3521, 103.8198, 10),
    Target("speedtest.tyo11.jp.leaseweb.net", 5201, "JP", "Tokyo", 35.6762, 139.6503, 10),
    Target("speedtest.syd12.au.leaseweb.net", 5201, "AU", "Sydney", -33.8688, 151.2093, 10),
)


def validate_host(value: str) -> str:
    value = value.strip()
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    labels = value.rstrip(".").split(".")
    if len(value) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels):
        raise ValueError("servidor de medição inválido")
    return value


def _key(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in normalized if not unicodedata.combining(c)).casefold().split())


def coordinates(location):
    try:
        lat, lon = location["latitude"], location["longitude"]
        if isinstance(lat, bool) or isinstance(lon, bool):
            return None
        lat, lon = float(lat), float(lon)
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (KeyError, TypeError, ValueError):
        pass
    return None


def distance_km(origin, destination):
    lat1, lon1, lat2, lon2 = map(math.radians, (*origin, *destination))
    a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def select_target(host=None, port=5201, *, location=None, targets=TARGETS):
    """Return the first geographically ranked destination, without probing."""
    return rank_targets(host, port, location=location, targets=targets)[0]


def rank_targets(host=None, port=5201, *, location=None, targets=TARGETS):
    """Manual host wins; otherwise order the finite catalog by geography.

    If IP geolocation has only a city or country, return an explicitly coarse
    match. If it has no location at all, fail rather than choose a random host.
    This function performs no network I/O and never ranks by measured speed.
    """
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("porta de medição inválida")
    if host and host.strip():
        return (Target(validate_host(host), port, mode="manual"),)
    location = location or {}
    available = [t for t in targets if coordinates({"latitude": t.latitude, "longitude": t.longitude})]
    if not available:
        raise TargetSelectionError("O catálogo não contém destinos geográficos válidos.")
    origin = coordinates(location)
    if origin:
        ranked = [(distance_km(origin, (t.latitude, t.longitude)), t) for t in available]
        ranked.sort(key=lambda pair: (round(pair[0], 3), -pair[1].capacity_gbps, pair[1].host, pair[1].port))
        return tuple(replace(target, distance_km=round(distance, 1)) for distance, target in ranked)
    return _coarse_targets(location, available)


def _coarse_targets(location, available):
    country, city = _key(location.get("country_code")), _key(location.get("city"))
    exact = [t for t in available if country and _key(t.country_code) == country and city and _key(t.city) == city]
    regional = [t for t in available if country and _key(t.country_code) == country]
    candidates = exact or regional
    if candidates:
        candidates.sort(key=lambda t: (-t.capacity_gbps, t.city, t.host, t.port))
        mode = "automatic-city" if exact else "automatic-country"
        return tuple(replace(target, mode=mode) for target in candidates)
    raise TargetSelectionError("Não foi possível detectar sua localização. Confirme país/cidade na configuração ou informe um servidor de medição opcional.")
