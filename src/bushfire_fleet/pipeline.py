"""End-to-end build from the committed snapshot to the gold tables and the site."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
from shapely.geometry import shape

from bushfire_fleet.assumptions import (
    ALT_COVER_MINUTES,
    CLIMATOLOGY_END,
    CLIMATOLOGY_START,
    COVER_MINUTES,
    CRUISE_KMH,
    N_AIRCRAFT,
    SCRAMBLE_MIN,
    SEVERE_FFDI,
    W_HOTSPOT,
    W_POP,
    W_WEATHER,
)
from bushfire_fleet.bases import in_study
from bushfire_fleet.ffdi import danger_band, fire_weather_frame
from bushfire_fleet.optimise import (
    assign_nearest,
    biggest_cities,
    covered_codes,
    flight_minutes_matrix,
    solve_placement,
    summarise,
)
from bushfire_fleet.pages import write_site
from bushfire_fleet.sampler import local_season_months
from bushfire_fleet.simulate import run_simulation
from bushfire_fleet.spatial import run_spatial

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"
OUTPUTS = ROOT / "outputs"
SITE = ROOT / "site"
SYD = ZoneInfo("Australia/Sydney")
SHORT = {
    "New South Wales": "NSW",
    "Victoria": "Vic",
    "Queensland": "Qld",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "Tas",
    "Northern Territory": "NT",
    "Australian Capital Territory": "ACT",
}


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((SNAPSHOT / "manifest.json").read_text())
    regions, bases = _load_dimensions()
    weather, forecast = _load_weather(regions)
    events, perf = _spatial(regions)
    regions = _attach_activity(regions, weather, events)
    minutes = flight_minutes_matrix(bases, regions)
    optimal_ids = solve_placement(bases, regions, minutes, COVER_MINUTES)
    baseline_ids = biggest_cities(bases, regions, N_AIRCRAFT)
    optimal = _round_summary(summarise(covered_codes(optimal_ids, regions, minutes, COVER_MINUTES), regions))
    baseline = _round_summary(summarise(covered_codes(baseline_ids, regions, minutes, COVER_MINUTES), regions))
    optimal_60 = _round_summary(summarise(covered_codes(optimal_ids, regions, minutes, ALT_COVER_MINUTES), regions))
    baseline_60 = _round_summary(summarise(covered_codes(baseline_ids, regions, minutes, ALT_COVER_MINUTES), regions))
    samples = _season_samples(weather)
    simulated = run_simulation(samples)
    facts = _facts(
        manifest, regions, bases, events, forecast, minutes,
        optimal_ids, baseline_ids, optimal, baseline, optimal_60, baseline_60, simulated,
    )
    _write_gold(regions, bases, events, weather, simulated, facts, optimal_ids, baseline_ids)
    _write_fixture(samples, regions)
    write_site(facts, SITE)
    (OUTPUTS / "perf.json").write_text(json.dumps(perf, indent=2) + "\n")
    (OUTPUTS / "summary.json").write_text(json.dumps(_summary(facts, perf), indent=2) + "\n")
    print(json.dumps(_summary(facts, perf), indent=2))


def _load_dimensions() -> tuple[list[dict], list[dict]]:
    boundaries = json.loads((SNAPSHOT / "sa4_boundaries.geojson").read_text())
    points = json.loads((SNAPSHOT / "sa4_points.geojson").read_text())
    population = pd.read_csv(SNAPSHOT / "population_sa4.csv", dtype={"sa4_code": str, "state_code": str})
    airports = pd.read_csv(SNAPSHOT / "airports.csv")
    point_lookup = {}
    for feature in points["features"]:
        geom = feature.get("geometry")
        if not geom:
            continue
        coords = geom["coordinates"][0] if geom["type"] == "MultiPoint" else geom["coordinates"]
        point_lookup[str(feature["properties"]["sa4_code_2021"]).zfill(3)] = (float(coords[0]), float(coords[1]))
    pop_lookup = {str(row.sa4_code).zfill(3): row for row in population.itertuples(index=False)}
    regions = []
    for feature in boundaries["features"]:
        props = feature["properties"]
        code = str(props["sa4_code_2021"]).zfill(3)
        if not in_study(props.get("state_code_2021"), props.get("sa4_name_2021"), feature.get("geometry") is not None):
            continue
        if code not in point_lookup or code not in pop_lookup:
            continue
        lon, lat = point_lookup[code]
        pop = pop_lookup[code]
        regions.append(
            {
                "sa4_code": code,
                "name": props["sa4_name_2021"],
                "state": props["state_name_2021"],
                "state_short": SHORT.get(props["state_name_2021"], props["state_name_2021"]),
                "population": int(pop.erp_2025),
                "lon": lon,
                "lat": lat,
                "geometry": feature["geometry"],
                "wkt": shape(feature["geometry"]).wkt,
            }
        )
    regions.sort(key=lambda region: region["sa4_code"])
    base_rows = []
    for row in airports.itertuples(index=False):
        base_rows.append(
            {
                "ident": row.ident,
                "name": row.name,
                "municipality": row.municipality if isinstance(row.municipality, str) else "",
                "lon": float(row.longitude),
                "lat": float(row.latitude),
                "runway_m": int(row.runway_m),
            }
        )
    base_rows.sort(key=lambda base: base["ident"])
    print(f"regions {len(regions)} bases {len(base_rows)}")
    return regions, base_rows


def _load_weather(regions: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame]:
    codes = {region["sa4_code"] for region in regions}
    daily = pd.read_parquet(SNAPSHOT / "weather_daily.parquet")
    forecast = pd.read_parquet(SNAPSHOT / "weather_forecast.parquet")
    daily["sa4_code"] = daily["sa4_code"].astype(str).str.zfill(3)
    forecast["sa4_code"] = forecast["sa4_code"].astype(str).str.zfill(3)
    daily = daily[daily["sa4_code"].isin(codes)]
    forecast = forecast[forecast["sa4_code"].isin(codes)]
    pieces = []
    for code, group in pd.concat([daily, forecast], ignore_index=True).groupby("sa4_code"):
        group = group.sort_values("date").drop_duplicates("date", keep="first")
        pieces.extend(fire_weather_frame(group.to_dict("records")))
    enriched = pd.DataFrame(pieces)
    history = enriched[enriched["date"] < forecast["date"].min()].copy()
    outlook = enriched[enriched["date"] >= forecast["date"].min()].copy()
    return history, outlook


def _spatial(regions: list[dict]) -> tuple[pd.DataFrame, dict]:
    hot = pd.read_parquet(SNAPSHOT / "hotspots.parquet")
    hot["day_local"] = hot["observed_at"].map(_sydney_day)
    local_path = OUTPUTS / "hotspots_local.parquet"
    hot.to_parquet(local_path, index=False)
    wkts = [{"sa4_code": region["sa4_code"], "wkt": region["wkt"]} for region in regions]
    events, perf = run_spatial(local_path, wkts)
    events["sa4_code"] = events["sa4_code"].astype(str).str.zfill(3)
    events = events.sort_values(["sa4_code", "day_local", "cell"]).reset_index(drop=True)
    print("spatial", perf, "events", len(events))
    return events, perf


def _attach_activity(regions: list[dict], weather: pd.DataFrame, events: pd.DataFrame) -> list[dict]:
    clim = weather[(weather["date"] >= CLIMATOLOGY_START) & (weather["date"] <= CLIMATOLOGY_END)]
    clim = clim[clim["ffdi"].notna()]
    severe = (
        clim.assign(severe=clim["ffdi"] >= SEVERE_FFDI)
        .groupby("sa4_code")["severe"]
        .sum()
        .div(4.0)
    )
    heat = events.groupby("sa4_code").size()
    for region in regions:
        code = region["sa4_code"]
        region["severe_days"] = float(severe.get(code, 0.0))
        region["heat"] = int(heat.get(code, 0))
    pop_total = sum(region["population"] for region in regions) or 1
    severe_total = sum(region["severe_days"] for region in regions) or 1
    heat_total = sum(region["heat"] for region in regions) or 1
    for region in regions:
        region["weight"] = (
            W_POP * region["population"] / pop_total
            + W_WEATHER * region["severe_days"] / severe_total
            + W_HOTSPOT * region["heat"] / heat_total
        )
    return regions


def _season_samples(weather: pd.DataFrame) -> dict[str, tuple[list[float], list[float]]]:
    clim = weather[(weather["date"] >= CLIMATOLOGY_START) & (weather["date"] <= CLIMATOLOGY_END)]
    clim = clim[clim["ffdi"].notna() & clim["tmax_c"].notna()]
    samples = {}
    for code, group in clim.groupby("sa4_code"):
        by_month: dict[int, list[float]] = {}
        for month_key, part in group.groupby(group["date"].str.slice(5, 7)):
            by_month[int(month_key)] = [float(v) for v in part["ffdi"]]
        monthly = {month: sum(values) / len(values) for month, values in by_month.items()}
        chosen_months = local_season_months(monthly)
        chosen = group[group["date"].str.slice(5, 7).astype(int).isin(chosen_months)].sort_values("date")
        if chosen.empty:
            continue
        samples[str(code)] = (
            [float(v) for v in chosen["ffdi"]],
            [float(v) for v in chosen["tmax_c"]],
        )
    print(f"simulation regions {len(samples)}")
    return samples


def _facts(manifest, regions, bases, events, forecast, minutes, optimal_ids, baseline_ids, optimal, baseline, optimal_60, baseline_60, simulated) -> dict:
    pop = {region["sa4_code"]: region["population"] for region in regions}
    severe_series = pd.Series({region["sa4_code"]: region["severe_days"] for region in regions})
    q75 = float(severe_series.quantile(0.75))
    median = float(severe_series.median())
    high = [region for region in regions if region["severe_days"] >= q75]
    above = [region for region in regions if region["severe_days"] >= median]
    pop_total = sum(region["population"] for region in regions) or 1
    heat_total = sum(region["heat"] for region in regions) or 1

    def share_pop(group):
        return 100.0 * sum(region["population"] for region in group) / pop_total

    def share_heat(group):
        return 100.0 * sum(region["heat"] for region in group) / heat_total

    state_heat = {}
    state_pop = {}
    state_severe_num = {}
    for region in regions:
        state_heat[region["state"]] = state_heat.get(region["state"], 0) + region["heat"]
        state_pop[region["state"]] = state_pop.get(region["state"], 0) + region["population"]
        state_severe_num[region["state"]] = state_severe_num.get(region["state"], 0.0) + region["severe_days"] * region["population"]
    heat_by_state = [
        {"name": state, "short": SHORT.get(state, state), "heat": count, "share": 100.0 * count / heat_total}
        for state, count in sorted(state_heat.items(), key=lambda item: (-item[1], item[0]))
    ]
    severe_by_state = []
    for state, population in state_pop.items():
        severe_by_state.append(
            {
                "name": state,
                "short": SHORT.get(state, state),
                "severe_days": state_severe_num[state] / population if population else 0.0,
            }
        )
    severe_by_state.sort(key=lambda row: (-row["severe_days"], row["name"]))
    top_state = heat_by_state[0]
    worst = max(regions, key=lambda region: (region["severe_days"], region["sa4_code"]))
    busiest = max(regions, key=lambda region: (region["heat"], region["sa4_code"]))
    top_plan_region = max(regions, key=lambda region: (region["weight"], region["sa4_code"]))

    sim_lookup = {row["sa4_code"]: row for row in simulated}
    weight_pop = sum(pop[code] for code in sim_lookup) or 1
    uniform = sum(pop[code] * sim_lookup[code]["severe_days_uniform"] for code in sim_lookup) / weight_pop
    hotter = sum(pop[code] * sim_lookup[code]["severe_days_hotter"] for code in sim_lookup) / weight_pop
    uplift = 0 if uniform < 0.05 else int(round(100.0 * (hotter - uniform) / uniform))

    loads = assign_nearest(optimal_ids, regions, minutes, COVER_MINUTES)
    base_lookup = {base["ident"]: base for base in bases}
    labels = _labels(base_lookup, optimal_ids + [ident for ident in baseline_ids if ident not in optimal_ids])
    base_loads = []
    for ident in optimal_ids:
        covered = loads.get(ident, [])
        base_loads.append(
            {
                "ident": ident,
                "label": labels[ident],
                "name": base_lookup[ident]["name"],
                "people": sum(region["population"] for region in covered),
                "heat": sum(region["heat"] for region in covered),
            }
        )
    base_loads.sort(key=lambda row: (-row["people"], row["ident"]))
    base_detail = []
    for ident in sorted(set(optimal_ids) | set(baseline_ids)):
        people_n = sum(region["population"] for region in loads.get(ident, [])) if ident in optimal_ids else 0
        heat_n = sum(region["heat"] for region in loads.get(ident, [])) if ident in optimal_ids else 0
        if ident in optimal_ids and ident in baseline_ids:
            role = "Recommended, and also in the biggest-cities line-up"
        elif ident in optimal_ids:
            role = "Recommended"
        else:
            role = "Biggest-cities line-up only"
        base_detail.append(
            {
                "ident": ident,
                "label": labels[ident],
                "name": base_lookup[ident]["name"],
                "people": people_n,
                "heat": heat_n,
                "role": role,
            }
        )

    days = sorted(events["day_local"].unique())
    heat_by_day = [{"label": _day_label(day), "count": int((events["day_local"] == day).sum())} for day in days]
    forecast_days = sorted(forecast["date"].unique())
    state_order = [row["name"] for row in sorted(severe_by_state, key=lambda item: item["name"])]
    # Keep a geographic reading order instead of alphabetical for the grid.
    preferred = [
        "Western Australia",
        "Northern Territory",
        "South Australia",
        "Queensland",
        "New South Wales",
        "Australian Capital Territory",
        "Victoria",
        "Tasmania",
    ]
    state_order = [state for state in preferred if state in state_pop]
    forecast_states = []
    peak = {"score": -1.0, "state": "", "day": "", "band": "Low"}
    severe_states = 0
    for state in state_order:
        codes = [region["sa4_code"] for region in regions if region["state"] == state]
        scores = []
        hit = False
        for day in forecast_days:
            chunk = forecast[(forecast["date"] == day) & (forecast["sa4_code"].isin(codes)) & forecast["ffdi"].notna()]
            score = int(round(float(chunk["ffdi"].max()))) if not chunk.empty else 0
            scores.append(score)
            if score >= SEVERE_FFDI:
                hit = True
            if score > peak["score"]:
                peak = {
                    "score": score,
                    "state": SHORT.get(state, state),
                    "day": _day_label(day),
                    "band": danger_band(score),
                }
        if hit:
            severe_states += 1
        forecast_states.append({"name": state, "short": SHORT.get(state, state), "scores": scores})

    def pack(rows, key):
        packed = []
        for region in rows:
            if key == "severe_days":
                metric = f"{region['severe_days']:.2f}"
            elif key == "weight":
                metric = f"{region['weight'] * 100:.2f}"
            elif key == "population":
                metric = f"{region['population']:,}"
            else:
                metric = f"{region['heat']:,}"
            packed.append(
                {
                    "name": region["name"],
                    "state": region["state_short"],
                    "population": region["population"],
                    "heat": region["heat"],
                    "severe_days": round(region["severe_days"], 2),
                    "weight": region["weight"],
                    "metric": metric,
                    key: region[key],
                }
            )
        return packed

    top_severe = pack(sorted(regions, key=lambda r: (-r["severe_days"], r["sa4_code"]))[:8], "severe_days")
    top_people = pack(sorted(regions, key=lambda r: (-r["population"], r["sa4_code"]))[:8], "population")
    top_heat = pack(sorted(regions, key=lambda r: (-r["heat"], r["sa4_code"]))[:8], "heat")
    top_plan = pack(sorted(regions, key=lambda r: (-r["weight"], r["sa4_code"]))[:8], "weight")

    opt_set, base_set = set(optimal_ids), set(baseline_ids)
    map_bases = []
    for ident in sorted(opt_set | base_set):
        if ident in opt_set and ident in base_set:
            kind = "both"
        elif ident in opt_set:
            kind = "recommended"
        else:
            kind = "baseline"
        base = base_lookup[ident]
        map_bases.append({"lon": base["lon"], "lat": base["lat"], "label": labels[ident], "kind": kind})

    map_regions = [
        {
            "code": region["sa4_code"],
            "name": region["name"],
            "geometry": region["geometry"],
            "severe_days": region["severe_days"],
            "population": region["population"],
            "heat": region["heat"],
            "weight": region["weight"],
        }
        for region in regions
    ]
    return {
        "when_label": manifest["accessed_at_aedt"],
        "tz_label": manifest["tz_label"],
        "n_regions": len(regions),
        "n_aircraft": N_AIRCRAFT,
        "cover_minutes": COVER_MINUTES,
        "population": pop_total,
        "high_quarter_population": sum(region["population"] for region in high),
        "high_quarter_pop_share": round(share_pop(high), 1),
        "high_quarter_heat_share": round(share_heat(high), 1),
        "median_danger_population": sum(region["population"] for region in above),
        "median_danger_pop_share": round(share_pop(above), 1),
        "median_danger_heat_share": round(share_heat(above), 1),
        "worst_region": {"name": worst["name"], "severe_days": round(worst["severe_days"], 1)},
        "busiest_heat_region": {"name": busiest["name"], "state": busiest["state_short"], "heat": busiest["heat"]},
        "top_plan_region": {"name": top_plan_region["name"]},
        "top_heat_state": {
            "name": top_state["name"],
            "short": top_state["short"],
            "heat": top_state["heat"],
            "share": round(top_state["share"], 1),
        },
        "fiercest_state": {"name": severe_by_state[0]["name"], "severe_days": round(severe_by_state[0]["severe_days"], 1)},
        "heat_events": int(len(events)),
        "heat_day_start": _day_label(days[0]),
        "heat_day_end": _day_label(days[-1]),
        "sim_uplift_pct": uplift,
        "sim_uniform": round(uniform, 2),
        "sim_hotter": round(hotter, 2),
        "optimal": optimal,
        "baseline": baseline,
        "optimal_60": optimal_60,
        "baseline_60": baseline_60,
        "heat_by_state": heat_by_state,
        "severe_by_state": severe_by_state,
        "top_severe": top_severe,
        "top_people": top_people,
        "top_heat": top_heat,
        "top_plan": top_plan,
        "base_loads": base_loads,
        "base_detail": base_detail,
        "recommended_labels": [row["label"] for row in base_loads],
        "baseline_labels": [labels[ident] for ident in baseline_ids],
        "heat_by_day": heat_by_day,
        "forecast_days": [_day_label(day) for day in forecast_days],
        "forecast_states": forecast_states,
        "forecast_peak": peak,
        "severe_forecast_states": severe_states,
        "map_regions": map_regions,
        "map_bases": map_bases,
        "assumption_rows": [
            ("Aircraft", f"{N_AIRCRAFT} large air tankers"),
            ("Cruise speed", f"{int(CRUISE_KMH)} km/h"),
            ("Time to get airborne", f"{int(SCRAMBLE_MIN)} minutes"),
            ("Counted as covered", f"The region's official location point is within {COVER_MINUTES} minutes"),
            ("Candidate bases", "Australian airports with a paved runway of at least 1,800 m and scheduled service, plus long-runway RAAF and naval fields on the public list"),
            ("Biggest-cities line-up", "The main airport, by runway length, in each of the six city areas with the most people living within 100 km"),
            ("People", "ABS estimated residents at 30 June 2025"),
            ("Dangerous weather", "Days from 2022 to 2025 when the fire-weather score reached the severe band"),
            ("This week's heat", "Clearer satellite detections, one count per small patch per day"),
            ("Hotter-day picture", "The same historical days, drawn more often when they were hotter"),
        ],
        "_optimal_ids": optimal_ids,
        "_baseline_ids": baseline_ids,
        "_bases": bases,
        "_simulated": simulated,
    }


def _labels(base_lookup: dict[str, dict], idents: list[str]) -> dict[str, str]:
    labels = {}
    used = set()
    for ident in idents:
        raw = _place_name(base_lookup[ident]["name"])
        if raw in used:
            raw = f"{raw} ({ident})"
        used.add(raw)
        labels[ident] = raw
    return labels


def _place_name(name: str) -> str:
    if "(" in name and ")" in name:
        inner = name.split("(", 1)[1].split(")", 1)[0].strip()
        if inner and "Nancy" not in inner and "Bird" not in inner and len(inner) <= 18:
            return inner
    text = name.split("(")[0].split("/")[0]
    for token in (" International", " Airport", " Regional", "RAAF Base "):
        text = text.replace(token, " ")
    text = " ".join(text.split()).strip(" -")
    first = text.split(" ")[0] if text else ""
    if first in {"Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Hobart", "Darwin", "Canberra", "Newcastle"} and text != first:
        return first
    if len(text) > 22:
        cut = text.rfind(" ", 0, 22)
        text = text[: cut if cut > 8 else 22].strip()
    return text or name


def _write_gold(regions, bases, events, weather, simulated, facts, optimal_ids, baseline_ids) -> None:
    base_lookup = {base["ident"]: base for base in bases}
    labels = _labels(base_lookup, optimal_ids + baseline_ids)
    placement = []
    for scenario, idents in (("recommended", optimal_ids), ("biggest_cities", baseline_ids)):
        for rank, ident in enumerate(idents, start=1):
            base = base_lookup[ident]
            placement.append(
                {
                    "scenario": scenario,
                    "ident": ident,
                    "name": base["name"],
                    "municipality": labels[ident],
                    "lon": base["lon"],
                    "lat": base["lat"],
                    "rank": rank,
                }
            )
    coverage = []
    for scenario, summary, minutes in (
        ("recommended", facts["optimal"], COVER_MINUTES),
        ("biggest_cities", facts["baseline"], COVER_MINUTES),
        ("recommended", facts["optimal_60"], ALT_COVER_MINUTES),
        ("biggest_cities", facts["baseline_60"], ALT_COVER_MINUTES),
    ):
        coverage.append({"scenario": scenario, "minutes": minutes, **summary})
    region_df = pd.DataFrame(
        [
            {
                "sa4_code": region["sa4_code"],
                "sa4_name": region["name"],
                "state_name": region["state"],
                "population": region["population"],
                "severe_days_per_year": round(region["severe_days"], 4),
                "hotspot_events": region["heat"],
                "weight": round(region["weight"], 6),
                "lon": region["lon"],
                "lat": region["lat"],
            }
            for region in regions
        ]
    )
    weather_df = weather[weather["ffdi"].notna()][
        ["sa4_code", "date", "tmax_c", "rh_min_pct", "wind_max_kmh", "precip_mm", "kbdi", "drought_factor", "ffdi"]
    ].copy()
    path = OUTPUTS / "fleet.duckdb"
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")
        con.register("region_df", region_df)
        con.register("events_df", events)
        con.register("weather_df", weather_df)
        con.register("placement_df", pd.DataFrame(placement))
        con.register("coverage_df", pd.DataFrame(coverage))
        con.register("sim_df", pd.DataFrame(simulated))
        con.execute("CREATE TABLE gold_region_risk AS SELECT * FROM region_df")
        con.execute("CREATE TABLE gold_hotspot_event AS SELECT * FROM events_df")
        con.execute("CREATE TABLE gold_fire_weather_day AS SELECT * FROM weather_df")
        con.execute("CREATE TABLE gold_placement AS SELECT * FROM placement_df")
        con.execute("CREATE TABLE gold_coverage_summary AS SELECT * FROM coverage_df")
        con.execute("CREATE TABLE gold_simulation AS SELECT * FROM sim_df")
    finally:
        con.close()


def _write_fixture(samples: dict, regions: list[dict]) -> None:
    ranked = sorted(regions, key=lambda region: (-region["weight"], region["sa4_code"]))[:8]
    lines = ["sa4_code,ffdi,tmax_c"]
    for region in ranked:
        ffdi_values, tmax_values = samples[region["sa4_code"]]
        step = max(1, len(ffdi_values) // 40)
        for ffdi, tmax in list(zip(ffdi_values, tmax_values, strict=True))[::step][:40]:
            lines.append(f"{region['sa4_code']},{ffdi:.2f},{tmax:.2f}")
    csv_text = "\n".join(lines) + "\n"
    fixture = ROOT / "k8s" / "ray" / "fixture.csv"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(csv_text)
    sim = (ROOT / "k8s" / "ray" / "sim.py").read_text()
    config = ROOT / "k8s" / "ray" / "configmap.yaml"
    config.write_text(
        "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: fire-sim\n  namespace: bushfire\ndata:\n"
        f"  sim.py: |\n{_indent(sim)}  fixture.csv: |\n{_indent(csv_text)}"
    )


def _indent(text: str) -> str:
    return "".join("    " + line + "\n" for line in text.splitlines())


def _round_summary(summary: dict) -> dict:
    rounded = dict(summary)
    for key in ("people_pct", "heat_pct", "weather_pct", "weight_pct"):
        rounded[key] = round(summary[key], 1)
    rounded["people"] = float(round(summary["people"]))
    return rounded


def _sydney_day(timestamp: str) -> str:
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(SYD)
    return moment.date().isoformat()


def _day_label(value: str) -> str:
    moment = date.fromisoformat(str(value)[:10])
    return f"{moment.day} {moment.strftime('%b')}"


def _summary(facts: dict, perf: dict) -> dict:
    return {
        "when": facts["when_label"],
        "regions": facts["n_regions"],
        "heat_events": facts["heat_events"],
        "high_quarter_population": facts["high_quarter_population"],
        "high_quarter_heat_share": facts["high_quarter_heat_share"],
        "sim_uplift_pct": facts["sim_uplift_pct"],
        "optimal_people_pct": facts["optimal"]["people_pct"],
        "baseline_people_pct": facts["baseline"]["people_pct"],
        "optimal_heat_pct": facts["optimal"]["heat_pct"],
        "baseline_heat_pct": facts["baseline"]["heat_pct"],
        "optimal_weather_pct": facts["optimal"]["weather_pct"],
        "baseline_weather_pct": facts["baseline"]["weather_pct"],
        "bases": [base["label"] for base in facts["base_loads"]],
        "worst_region": facts["worst_region"]["name"],
        "fiercest_state": facts["fiercest_state"]["name"],
        "top_heat_state": facts["top_heat_state"]["name"],
        "sim_uniform": facts["sim_uniform"],
        "sim_hotter": facts["sim_hotter"],
        "perf": perf,
    }


if __name__ == "__main__":
    main()
