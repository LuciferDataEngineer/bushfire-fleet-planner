from bushfire_fleet.optimise import biggest_cities, flight_minutes_matrix, solve_placement


def test_single_aircraft_goes_to_the_heaviest_region():
    bases = [
        {"ident": "X", "lon": 0.0, "lat": 0.0},
        {"ident": "Y", "lon": 10.0, "lat": 0.0},
        {"ident": "Z", "lon": 20.0, "lat": 0.0},
    ]
    regions = [
        {"sa4_code": "A", "lon": 0.0, "lat": 0.0, "weight": 0.05, "population": 10, "heat": 0, "severe_days": 0},
        {"sa4_code": "B", "lon": 10.0, "lat": 0.0, "weight": 0.90, "population": 10, "heat": 0, "severe_days": 0},
        {"sa4_code": "C", "lon": 20.0, "lat": 0.0, "weight": 0.05, "population": 10, "heat": 0, "severe_days": 0},
    ]
    minutes = flight_minutes_matrix(bases, regions)
    chosen = solve_placement(bases, regions, minutes, 90, n_aircraft=1, seed=3)
    assert chosen == ["Y"]


def test_biggest_cities_follows_population_and_does_not_reuse_a_base():
    bases = [
        {"ident": "A", "lon": 0.0, "lat": 0.0},
        {"ident": "B", "lon": 5.0, "lat": 0.0},
        {"ident": "C", "lon": 10.0, "lat": 0.0},
    ]
    regions = [
        {"sa4_code": "1", "lon": 0.0, "lat": 0.0, "population": 100, "weight": 0.2, "heat": 0, "severe_days": 0},
        {"sa4_code": "2", "lon": 0.2, "lat": 0.0, "population": 90, "weight": 0.2, "heat": 0, "severe_days": 0},
        {"sa4_code": "3", "lon": 10.0, "lat": 0.0, "population": 80, "weight": 0.2, "heat": 0, "severe_days": 0},
    ]
    chosen = biggest_cities(bases, regions, n_aircraft=2)
    assert chosen[0] == "A"
    assert "C" in chosen
    assert len(chosen) == 2
