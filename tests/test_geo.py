from bushfire_fleet.geo import flight_minutes, haversine_km


def test_sydney_melbourne_distance():
    distance = haversine_km(151.2093, -33.8688, 144.9631, -37.8136)
    assert 700 <= distance <= 730


def test_flight_time_adds_the_scramble():
    assert flight_minutes(0) == 15
    assert flight_minutes(450) == 75
