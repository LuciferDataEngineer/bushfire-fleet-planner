"""Maximal covering location problem for a fixed number of aircraft."""

from __future__ import annotations

from ortools.sat.python import cp_model

from bushfire_fleet.assumptions import N_AIRCRAFT, SEED
from bushfire_fleet.geo import flight_minutes, haversine_km


def flight_minutes_matrix(bases: list[dict], regions: list[dict]) -> dict[tuple[str, str], float]:
    matrix: dict[tuple[str, str], float] = {}
    for base in bases:
        for region in regions:
            distance = haversine_km(base["lon"], base["lat"], region["lon"], region["lat"])
            matrix[(base["ident"], region["sa4_code"])] = flight_minutes(distance)
    return matrix


def covered_codes(
    selected: list[str],
    regions: list[dict],
    minutes: dict[tuple[str, str], float],
    limit: float,
) -> set[str]:
    chosen = set(selected)
    covered = set()
    for region in regions:
        code = region["sa4_code"]
        for ident in chosen:
            if minutes[(ident, code)] <= limit:
                covered.add(code)
                break
    return covered


def summarise(covered: set[str], regions: list[dict]) -> dict[str, float]:
    pop = sum(r["population"] for r in regions) or 1
    heat = sum(r["heat"] for r in regions) or 1
    weather = sum(r["severe_days"] for r in regions) or 1
    weight = sum(r["weight"] for r in regions) or 1
    pop_c = sum(r["population"] for r in regions if r["sa4_code"] in covered)
    heat_c = sum(r["heat"] for r in regions if r["sa4_code"] in covered)
    weather_c = sum(r["severe_days"] for r in regions if r["sa4_code"] in covered)
    weight_c = sum(r["weight"] for r in regions if r["sa4_code"] in covered)
    return {
        "people": float(pop_c),
        "people_pct": 100.0 * pop_c / pop,
        "heat_pct": 100.0 * heat_c / heat,
        "weather_pct": 100.0 * weather_c / weather,
        "weight_pct": 100.0 * weight_c / weight,
    }


def solve_placement(
    bases: list[dict],
    regions: list[dict],
    minutes: dict[tuple[str, str], float],
    limit: float,
    n_aircraft: int = N_AIRCRAFT,
    seed: int = SEED,
) -> list[str]:
    """Choose n bases to maximise the weighted mix of people, weather and heat.

    A tiny penalty on later base ids breaks ties the same way every run.
    """
    ordered = sorted(bases, key=lambda base: base["ident"])
    model = cp_model.CpModel()
    x = [model.new_bool_var(base["ident"]) for base in ordered]
    y = [model.new_bool_var(region["sa4_code"]) for region in regions]
    model.add(sum(x) == n_aircraft)
    for i, region in enumerate(regions):
        covers = [
            x[j]
            for j, base in enumerate(ordered)
            if minutes[(base["ident"], region["sa4_code"])] <= limit
        ]
        if covers:
            model.add(y[i] <= sum(covers))
        else:
            model.add(y[i] == 0)
    terms = []
    for i, region in enumerate(regions):
        terms.append(int(round(region["weight"] * 1_000_000)) * y[i])
    for j, var in enumerate(x):
        terms.append(-j * var)
    model.maximize(sum(terms))
    solver = cp_model.CpSolver()
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 1
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"placement solver status {solver.status_name(status)}")
    return [base["ident"] for base, var in zip(ordered, x, strict=True) if solver.value(var)]


def biggest_cities(
    bases: list[dict],
    regions: list[dict],
    n_aircraft: int = N_AIRCRAFT,
    city_km: float = 100.0,
    separation_km: float = 150.0,
) -> list[str]:
    """One airport in each of the largest cities.

    A city score is the population living within 100 km of the airport. A second
    airport in the same city (within 150 km of one already chosen) is skipped.
    """
    scored: list[tuple[int, dict]] = []
    for base in bases:
        nearby = 0
        for region in regions:
            if haversine_km(base["lon"], base["lat"], region["lon"], region["lat"]) <= city_km:
                nearby += int(region["population"])
        scored.append((nearby, base))
    scored.sort(key=lambda item: (-item[0], item[1]["ident"]))
    chosen: list[dict] = []
    pool = list(scored)
    while pool and len(chosen) < n_aircraft:
        _seed_pop, seed = pool.pop(0)
        cluster = [seed]
        kept: list[tuple[int, dict]] = []
        for pop, base in pool:
            if haversine_km(base["lon"], base["lat"], seed["lon"], seed["lat"]) < separation_km:
                cluster.append(base)
            else:
                kept.append((pop, base))
        pool = kept
        winner = min(cluster, key=lambda base: (-int(base.get("runway_m", 0)), base["ident"]))
        chosen.append(winner)
    return [base["ident"] for base in chosen]


def assign_nearest(selected: list[str], regions: list[dict], minutes: dict[tuple[str, str], float], limit: float) -> dict[str, list[dict]]:
    buckets = {ident: [] for ident in selected}
    for region in regions:
        options = [
            (minutes[(ident, region["sa4_code"])], ident)
            for ident in selected
            if minutes[(ident, region["sa4_code"])] <= limit
        ]
        if not options:
            continue
        _mins, ident = min(options)
        buckets[ident].append(region)
    return buckets
