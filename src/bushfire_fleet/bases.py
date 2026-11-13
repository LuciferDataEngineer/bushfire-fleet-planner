"""Candidate air-base rule, applied to the OurAirports public-domain extract."""

from __future__ import annotations

from bushfire_fleet.assumptions import MILITARY_EXTRA_IDENTS, MIN_RUNWAY_M

PAVED_TOKENS = ("asp", "con", "bit", "pem", "paved", "sealed", "mac")


def longest_paved_runway_m(runways: list[dict]) -> float:
    best = 0.0
    for row in runways:
        raw = row.get("length_ft") or ""
        try:
            length_ft = float(raw)
        except (TypeError, ValueError):
            continue
        surface = (row.get("surface") or "").lower()
        if not any(token in surface for token in PAVED_TOKENS):
            continue
        best = max(best, length_ft * 0.3048)
    return best


def is_candidate(airport: dict, runway_m: float) -> bool:
    """Australian large/medium airport with a paved runway of at least 1,800 m.

    Scheduled airports and large airports qualify. So do fields whose name
    contains RAAF, plus Tindal (YPTN) and Nowra (YSNW), which are long-runway
    military fields whose OurAirports names omit the word RAAF.
    """
    if airport.get("iso_country") != "AU":
        return False
    if airport.get("type") not in {"large_airport", "medium_airport"}:
        return False
    if runway_m < MIN_RUNWAY_M:
        return False
    name = airport.get("name") or ""
    ident = airport.get("ident") or ""
    if airport.get("scheduled_service") == "yes":
        return True
    if airport.get("type") == "large_airport":
        return True
    if "RAAF" in name:
        return True
    return ident in MILITARY_EXTRA_IDENTS


def in_study(state_code: str | None, name: str | None, has_geometry: bool) -> bool:
    """Geographic SA4s on the mainland, Tasmania and the ACT.

    Drops migratory/offshore/no-usual-address codes (they have no polygon) and
    Other Territories, which sit too far away to draw or to base aircraft for
    a continental plan.
    """
    if not has_geometry:
        return False
    if str(state_code) == "9":
        return False
    label = name or ""
    if "Migratory" in label or "No usual address" in label:
        return False
    return True
