"""Slim Ray season simulation for the KubeRay job.

The sampler matches the local study: historical days only, reweighted toward
hotter days. The fixture is a real extract, not invented weather.
"""

from __future__ import annotations

import csv
import os
import zlib

import numpy as np
import ray

SEVERE = 50.0


def region_seed(base_seed: int, code: str) -> int:
    return (base_seed + zlib.crc32(code.encode("utf-8"))) % (2**31 - 1)


def mean_severe_days(ffdi, tmax, n_seasons, season_days, seed, beta, hotter):
    rng = np.random.default_rng(seed)
    weights = None
    if hotter:
        sd = float(np.std(tmax))
        if sd < 1e-9:
            sd = 1.0
        raw = np.exp(beta * (tmax - float(np.mean(tmax))) / sd)
        total = float(raw.sum())
        weights = None if total <= 0 else raw / total
    total_days = 0.0
    n = int(ffdi.shape[0])
    for _ in range(n_seasons):
        idx = rng.choice(n, size=season_days, replace=True, p=weights)
        total_days += float(np.count_nonzero(ffdi[idx] >= SEVERE))
    return total_days / n_seasons


def load(path: str) -> dict[str, tuple[list[float], list[float]]]:
    groups: dict[str, list[tuple[float, float]]] = {}
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            groups.setdefault(row["sa4_code"], []).append((float(row["ffdi"]), float(row["tmax_c"])))
    return {code: groups[code] for code in sorted(groups)}


@ray.remote
def run_one(code, pairs, n_seasons, season_days, seed, beta):
    ffdi = np.asarray([pair[0] for pair in pairs], dtype=np.float64)
    tmax = np.asarray([pair[1] for pair in pairs], dtype=np.float64)
    uniform = mean_severe_days(ffdi, tmax, n_seasons, season_days, seed, beta, False)
    hotter = mean_severe_days(ffdi, tmax, n_seasons, season_days, seed, beta, True)
    return {"sa4_code": code, "uniform": uniform, "hotter": hotter}


def main() -> None:
    path = os.environ.get("FIXTURE_PATH", "/opt/sim/fixture.csv")
    n_seasons = int(os.environ.get("N_SEASONS", "12"))
    season_days = int(os.environ.get("SEASON_DAYS", "30"))
    seed = int(os.environ.get("SEED", "15"))
    beta = float(os.environ.get("BETA", "0.8"))
    groups = load(path)
    if os.environ.get("RAY_ADDRESS"):
        ray.init(address=os.environ["RAY_ADDRESS"], ignore_reinit_error=True)
    else:
        ray.init(num_cpus=2, include_dashboard=False, logging_level="ERROR", ignore_reinit_error=True)
    futures = [
        run_one.remote(code, groups[code], n_seasons, season_days, region_seed(seed, code), beta)
        for code in groups
    ]
    rows = sorted(ray.get(futures), key=lambda row: row["sa4_code"])
    hotter = sum(row["hotter"] for row in rows) / len(rows)
    uniform = sum(row["uniform"] for row in rows) / len(rows)
    print(
        f"RAYJOB_OK regions={len(rows)} mean_uniform={uniform:.4f} mean_hotter={hotter:.4f}",
        flush=True,
    )


if __name__ == "__main__":
    main()
