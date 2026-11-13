import math

from bushfire_fleet.ffdi import drought_factor, ffdi, fire_weather_frame, kbdi_step


def test_ffdi_matches_published_expression():
    # Noble, Bary and Gill (1980): DF 10, RH 10%, 35 C, 40 km/h.
    score = ffdi(10, 10, 35, 40)
    assert math.isclose(score, 72.9518, abs_tol=1e-3)


def test_hot_day_scores_higher_than_a_mild_day():
    hot = ffdi(10, 12, 38, 45)
    mild = ffdi(3, 70, 18, 10)
    assert hot > mild
    assert mild > 0


def test_kbdi_stays_in_range_and_falls_after_heavy_rain():
    dry = kbdi_step(80, 35, 0, 600)
    assert 80 < dry <= 203.2
    wet = kbdi_step(dry, 20, 40, 600)
    assert wet < dry
    assert kbdi_step(1, 10, 50, 600) >= 0


def test_drought_factor_is_clamped_and_rain_lowers_it():
    parched = drought_factor(180, 40, 0)
    soaked = drought_factor(40, 0, 50)
    assert parched == 10
    assert 1 <= soaked < parched


def test_series_carries_drought_forward():
    rows = [
        {"date": "2022-01-01", "tmax_c": 35, "rh_min_pct": 15, "wind_max_kmh": 30, "precip_mm": 0},
        {"date": "2022-01-02", "tmax_c": 36, "rh_min_pct": 12, "wind_max_kmh": 35, "precip_mm": 0},
        {"date": "2022-01-03", "tmax_c": 22, "rh_min_pct": 80, "wind_max_kmh": 10, "precip_mm": 40},
    ]
    out = fire_weather_frame(rows, annual_rain_mm=500)
    assert out[1]["ffdi"] > out[2]["ffdi"]
    assert out[1]["kbdi"] >= out[0]["kbdi"]
    assert out[2]["kbdi"] < out[1]["kbdi"]
