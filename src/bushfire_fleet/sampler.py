"""Seeded season sampler shared by the local Ray run and the unit tests."""

from __future__ import annotations

import zlib

import numpy as np

from bushfire_fleet.assumptions import EL_NINO_TEMP_BETA, SEVERE_FFDI


def region_seed(base_seed: int, sa4_code: str) -> int:
    mixed = (base_seed + zlib.crc32(sa4_code.encode("utf-8"))) % (2**31 - 1)
    return int(mixed)


def sample_weights(tmax: np.ndarray, beta: float, hotter: bool) -> np.ndarray | None:
    """Uniform draw, or a reweight toward hotter days that actually occurred.

    No synthetic weather is created. The hotter picture only changes how often
    each historical day is drawn.
    """
    if not hotter:
        return None
    sd = float(np.std(tmax))
    if sd < 1e-9:
        sd = 1.0
    weights = np.exp(beta * (tmax - float(np.mean(tmax))) / sd)
    total = float(weights.sum())
    if total <= 0:
        return None
    return weights / total


def mean_severe_days(
    ffdi: np.ndarray,
    tmax: np.ndarray,
    n_seasons: int,
    season_days: int,
    seed: int,
    beta: float = EL_NINO_TEMP_BETA,
    hotter: bool = False,
    severe_at: float = SEVERE_FFDI,
) -> float:
    rng = np.random.default_rng(seed)
    weights = sample_weights(tmax, beta, hotter)
    total = 0.0
    n = int(ffdi.shape[0])
    if n == 0:
        return 0.0
    for _ in range(n_seasons):
        idx = rng.choice(n, size=season_days, replace=True, p=weights)
        total += float(np.count_nonzero(ffdi[idx] >= severe_at))
    return total / n_seasons


def local_season_months(monthly_mean: dict[int, float]) -> set[int]:
    """October–March unless the fiercest month falls in the northern dry season."""
    if not monthly_mean:
        return {10, 11, 12, 1, 2, 3}
    peak = max(monthly_mean, key=lambda month: (monthly_mean[month], -month))
    if peak in {5, 6, 7, 8, 9, 10}:
        return {4, 5, 6, 7, 8, 9, 10}
    return {10, 11, 12, 1, 2, 3}
