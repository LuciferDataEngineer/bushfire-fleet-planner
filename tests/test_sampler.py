import numpy as np

from bushfire_fleet.sampler import local_season_months, mean_severe_days, region_seed


def test_sampler_is_repeatable():
    ffdi = np.linspace(10, 90, 60)
    tmax = np.linspace(18, 42, 60)
    first = mean_severe_days(ffdi, tmax, 30, 20, 15, 0.8, hotter=True)
    second = mean_severe_days(ffdi, tmax, 30, 20, 15, 0.8, hotter=True)
    assert first == second


def test_hotter_draw_finds_more_severe_days_when_heat_and_danger_move_together():
    tmax = np.linspace(15, 42, 90)
    ffdi = tmax * 2.8
    uniform = mean_severe_days(ffdi, tmax, 300, 40, 11, 0.8, hotter=False)
    hotter = mean_severe_days(ffdi, tmax, 300, 40, 11, 0.8, hotter=True)
    assert hotter > uniform + 1


def test_region_seeds_do_not_collide_for_neighbours():
    assert region_seed(15, "101") != region_seed(15, "102")


def test_northern_peak_selects_the_dry_season():
    monthly = {month: 10.0 for month in range(1, 13)}
    monthly[8] = 40.0
    assert local_season_months(monthly) == {4, 5, 6, 7, 8, 9, 10}
    monthly = {month: 10.0 for month in range(1, 13)}
    monthly[1] = 40.0
    assert 1 in local_season_months(monthly)
    assert 6 not in local_season_months(monthly)
