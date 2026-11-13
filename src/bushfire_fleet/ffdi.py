"""McArthur Mark 5 forest fire danger index and a metric Keetch-Byram drought index.

The drought factor follows Griffiths (1999). The daily KBDI step is the metric
form of Keetch and Byram (1968): US units converted with 0.254 mm per index point,
a 5.08 mm interception allowance, and daily maximum temperature.
"""

from __future__ import annotations

import math

from bushfire_fleet.assumptions import (
    CATASTROPHIC_FFDI,
    EXTREME_FFDI,
    HIGH_FFDI,
    SEVERE_FFDI,
    VERY_HIGH_FFDI,
)

KBDI_CAP_MM = 800.0 * 0.254
INTERCEPTION_MM = 5.08
RAIN_RESET_MM = 5.0


def kbdi_step(kbdi_prev: float, temp_c: float, precip_mm: float, annual_rain_mm: float) -> float:
    """Advance metric KBDI (mm of soil-water deficit, capped near 203) by one day."""
    rain = max(0.0, precip_mm)
    net_rain = rain - INTERCEPTION_MM if rain > INTERCEPTION_MM else 0.0
    kbdi = max(0.0, kbdi_prev - net_rain)

    temp_f = temp_c * 9.0 / 5.0 + 32.0
    annual_in = max(0.0, annual_rain_mm) / 25.4
    q = kbdi / 0.254
    if temp_f <= 50.0:
        increment = 0.0
    else:
        numerator = (800.0 - q) * (0.968 * math.exp(0.0486 * temp_f) - 8.30) * 0.001
        denominator = 1.0 + 10.88 * math.exp(-0.0441 * annual_in)
        increment = max(0.0, numerator / denominator)
    q = min(800.0, max(0.0, q + increment))
    return min(KBDI_CAP_MM, q * 0.254)


def drought_factor(kbdi: float, days_since_rain: int, rain_event_mm: float) -> float:
    """Griffiths (1999) drought factor, clamped to the 1–10 range used by FFDI."""
    n = max(0, days_since_rain)
    p = max(0.0, rain_event_mm)
    power = (n + 1) ** 1.5
    numerator = (kbdi + 104.0) * power
    denominator = 3.52 * power + p - 1.0
    if denominator <= 0:
        raw = 10.0
    else:
        raw = 0.191 * numerator / denominator
    return min(10.0, max(1.0, raw))


def ffdi(drought: float, rh_pct: float, temp_c: float, wind_kmh: float) -> float:
    """McArthur Mark 5 forest fire danger index (Noble, Bary and Gill, 1980)."""
    df = min(10.0, max(1.0, drought))
    value = 2.0 * math.exp(
        -0.450
        + 0.987 * math.log(df)
        - 0.0345 * rh_pct
        + 0.0338 * temp_c
        + 0.0234 * wind_kmh
    )
    return max(0.0, value)


def danger_band(score: float) -> str:
    if score >= CATASTROPHIC_FFDI:
        return "Catastrophic"
    if score >= EXTREME_FFDI:
        return "Extreme"
    if score >= SEVERE_FFDI:
        return "Severe"
    if score >= VERY_HIGH_FFDI:
        return "Very high"
    if score >= HIGH_FFDI:
        return "High"
    return "Low"


def fire_weather_frame(rows: list[dict], annual_rain_mm: float | None = None) -> list[dict]:
    """Add KBDI, drought factor and FFDI to daily weather rows sorted by date.

    Rows need date, tmax_c, rh_min_pct, wind_max_kmh, precip_mm. The first year
    of a series is a spin-up for KBDI; callers drop it from the climatology.
    """
    ordered = sorted(rows, key=lambda r: r["date"])
    if annual_rain_mm is None:
        total = 0.0
        for row in ordered:
            if row.get("precip_mm") is not None:
                total += float(row["precip_mm"])
        span_days = 365.25
        if len(ordered) >= 2:
            span_days = max(span_days, _days_between(ordered[0]["date"], ordered[-1]["date"]))
        annual_rain_mm = total / (span_days / 365.25)

    kbdi = 0.0
    days_since = 0
    rain_event = 0.0
    seen_rain = False
    out = []
    for row in ordered:
        precip = 0.0 if row.get("precip_mm") is None else float(row["precip_mm"])
        temp = row.get("tmax_c")
        temp_for_kbdi = 15.0 if temp is None else float(temp)
        kbdi = kbdi_step(kbdi, temp_for_kbdi, precip, annual_rain_mm)
        if precip >= RAIN_RESET_MM:
            days_since = 0
            rain_event = precip
            seen_rain = True
        else:
            if seen_rain:
                days_since += 1
            else:
                days_since += 1
                rain_event = 0.0
        df = drought_factor(kbdi, days_since, rain_event)
        score = None
        if row.get("tmax_c") is not None and row.get("rh_min_pct") is not None and row.get("wind_max_kmh") is not None:
            score = ffdi(df, float(row["rh_min_pct"]), float(row["tmax_c"]), float(row["wind_max_kmh"]))
        enriched = dict(row)
        enriched["kbdi"] = round(kbdi, 2)
        enriched["drought_factor"] = round(df, 3)
        enriched["ffdi"] = None if score is None else round(score, 2)
        out.append(enriched)
    return out


def _days_between(start: str, end: str) -> float:
    from datetime import date

    a = date.fromisoformat(start)
    b = date.fromisoformat(end)
    return max(1.0, float((b - a).days))
