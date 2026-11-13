"""Distances and flying time for the coverage test."""

from __future__ import annotations

import math

from bushfire_fleet.assumptions import CRUISE_KMH, SCRAMBLE_MIN


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def flight_minutes(
    distance_km: float,
    cruise_kmh: float = CRUISE_KMH,
    scramble_min: float = SCRAMBLE_MIN,
) -> float:
    return scramble_min + distance_km / cruise_kmh * 60.0
