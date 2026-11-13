from bushfire_fleet.bases import in_study, is_candidate, longest_paved_runway_m


def test_candidate_rule():
    scheduled = {
        "iso_country": "AU",
        "type": "medium_airport",
        "scheduled_service": "yes",
        "name": "Dubbo",
        "ident": "YSDU",
    }
    assert is_candidate(scheduled, 1800)
    assert not is_candidate(scheduled, 1700)
    richmond = {
        "iso_country": "AU",
        "type": "medium_airport",
        "scheduled_service": "no",
        "name": "RAAF Base Richmond",
        "ident": "YSRI",
    }
    assert is_candidate(richmond, 2134)
    tindal = {
        "iso_country": "AU",
        "type": "medium_airport",
        "scheduled_service": "no",
        "name": "Tindal Airport",
        "ident": "YPTN",
    }
    assert is_candidate(tindal, 2700)
    overseas = dict(scheduled, iso_country="NZ")
    assert not is_candidate(overseas, 2500)


def test_paved_runway_ignores_grass():
    metres = longest_paved_runway_m(
        [
            {"length_ft": "3000", "surface": "GRS"},
            {"length_ft": "6000", "surface": "ASP"},
        ]
    )
    assert 1800 < metres < 1900


def test_study_regions_drop_offshore_and_non_geographic_codes():
    assert in_study("1", "Capital Region", True)
    assert not in_study("9", "Other Territories", True)
    assert not in_study("1", "Migratory - Offshore - Shipping (NSW)", False)
    assert not in_study("2", "No usual address (Vic.)", False)
