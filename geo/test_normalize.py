import pytest

from geo.normalize import normalize_name, place_name_variants


@pytest.mark.parametrize(
    ("csv_name", "census_name"),
    [
        ("Saint Louis", "St. Louis"),
        ("Mc Calla", "McCalla"),
        ("Mcallen", "McAllen"),
        ("Winston Salem", "Winston-Salem"),
        ("De Forest", "DeForest"),
        ("Sault Sainte Marie", "Sault Ste. Marie"),
        ("Mount Vernon", "Mt. Vernon"),
        ("Fort Wayne", "Ft. Wayne"),
        ("O Fallon", "O'Fallon"),
        ("La Place", "LaPlace"),
        ("  Effingham                    ", "Effingham"),
    ],
)
def test_csv_and_census_spellings_normalize_to_the_same_key(csv_name, census_name):
    assert normalize_name(csv_name) == normalize_name(census_name)


def test_different_places_stay_different():
    assert normalize_name("Saint Johns") != normalize_name("Johns")
    assert normalize_name("Mount Pleasant") != normalize_name("Pleasant")


def test_accents_are_folded():
    assert normalize_name("Española") == normalize_name("Espanola")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Abanda CDP", ("Abanda", [])),
        ("St. Louis city", ("St. Louis", [])),
        ("Union City city", ("Union City", [])),
        ("Big Cabin town", ("Big Cabin", [])),
        ("Indianapolis city (balance)", ("Indianapolis", [])),
        (
            "Nashville-Davidson metropolitan government (balance)",
            ("Nashville-Davidson", ["Nashville"]),
        ),
        (
            "Louisville/Jefferson County metro government (balance)",
            ("Louisville/Jefferson County", ["Louisville"]),
        ),
        ("Winston-Salem city", ("Winston-Salem", [])),
    ],
)
def test_place_name_variants_strip_census_suffixes(raw, expected):
    assert place_name_variants(raw) == expected
