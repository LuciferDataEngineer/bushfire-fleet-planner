from bushfire_fleet.story import build_copy


def _facts(**overrides):
    facts = {
        "optimal": {"people_pct": 80.0, "heat_pct": 70.0, "weather_pct": 75.0, "people": 20_000_000},
        "baseline": {"people_pct": 74.0, "heat_pct": 60.0, "weather_pct": 68.0, "people": 18_000_000},
        "baseline_60": {"people_pct": 70.0, "heat_pct": 20.0, "weather_pct": 30.0, "people": 17_000_000},
        "recommended_labels": ["Tamworth", "Mildura"],
        "baseline_labels": ["Sydney", "Melbourne"],
        "high_quarter_population": 4_200_000,
        "high_quarter_pop_share": 16.0,
        "high_quarter_heat_share": 55.0,
        "median_danger_population": 9_000_000,
        "median_danger_pop_share": 35.0,
        "median_danger_heat_share": 62.0,
        "worst_region": {"name": "Far West and Orana", "severe_days": 18.2},
        "busiest_heat_region": {"name": "Queensland - Outback", "state": "Qld", "heat": 400},
        "top_plan_region": {"name": "Queensland - Outback"},
        "top_heat_state": {"name": "Queensland", "short": "Qld", "heat": 900, "share": 48.0},
        "fiercest_state": {"name": "Northern Territory"},
        "n_regions": 89,
        "n_aircraft": 6,
        "heat_events": 2400,
        "heat_day_start": "11 Nov",
        "heat_day_end": "14 Nov",
        "tz_label": "AEDT",
        "sim_uplift_pct": 22,
        "sim_uniform": 1.4,
        "sim_hotter": 4.9,
        "optimal_60": {"people_pct": 40.0, "heat_pct": 10.0, "weather_pct": 20.0, "people": 10_000_000},
        "forecast_days": ["14 Nov", "15 Nov"],
        "forecast_peak": {"score": 42, "band": "Very high", "state": "Qld", "day": "16 Nov"},
        "severe_forecast_states": 0,
    }
    facts.update(overrides)
    return facts


def test_fleet_banner_states_both_coverages():
    text = build_copy(_facts())["fleet"]["banner"]
    assert "80.0%" in text
    assert "74.0%" in text
    assert "70.0%" in text
    assert "Tamworth" in text


def test_meaning_states_the_shorter_window():
    text = build_copy(_facts())["fleet"]["meaning"]
    assert "60 minutes" in text
    assert "40.0%" in text


def test_copy_avoids_tool_names():
    blob = str(build_copy(_facts())).lower()
    for word in ("sedona", "duckdb", "spark", "or-tools", "ffdi", "mcarthur", "kubernetes", "monte carlo"):
        assert word not in blob
