"""Ray season simulation. Each region is one deterministic task."""

from __future__ import annotations

import ray

from bushfire_fleet.assumptions import EL_NINO_TEMP_BETA, N_SEASONS, SEASON_DAYS, SEED
from bushfire_fleet.sampler import mean_severe_days, region_seed


@ray.remote
def _simulate_region(
    sa4_code: str,
    ffdi_values: list[float],
    tmax_values: list[float],
    n_seasons: int,
    season_days: int,
    seed: int,
    beta: float,
) -> dict:
    import numpy as np

    ffdi = np.asarray(ffdi_values, dtype=np.float64)
    tmax = np.asarray(tmax_values, dtype=np.float64)
    uniform = mean_severe_days(ffdi, tmax, n_seasons, season_days, seed, beta, hotter=False)
    hotter = mean_severe_days(ffdi, tmax, n_seasons, season_days, seed, beta, hotter=True)
    return {
        "sa4_code": sa4_code,
        "severe_days_uniform": round(uniform, 4),
        "severe_days_hotter": round(hotter, 4),
    }


def run_simulation(
    samples: dict[str, tuple[list[float], list[float]]],
    n_seasons: int = N_SEASONS,
    season_days: int = SEASON_DAYS,
    seed: int = SEED,
    beta: float = EL_NINO_TEMP_BETA,
    num_cpus: int = 2,
) -> list[dict]:
    ray.init(num_cpus=num_cpus, include_dashboard=False, logging_level="ERROR", ignore_reinit_error=True)
    try:
        futures = []
        for code in sorted(samples):
            ffdi_values, tmax_values = samples[code]
            futures.append(
                _simulate_region.remote(
                    code,
                    ffdi_values,
                    tmax_values,
                    n_seasons,
                    season_days,
                    region_seed(seed, code),
                    beta,
                )
            )
        rows = ray.get(futures)
    finally:
        ray.shutdown()
    return sorted(rows, key=lambda row: row["sa4_code"])
