from geo.gazetteer import build_places

HEADER = ["USPS", "NAME", "ALAND", "INTPTLAT", "INTPTLONG"]


def row(state, name, lat=1.0, lon=2.0, aland=100):
    return dict(zip(HEADER, [state, name, str(aland), str(lat), str(lon)], strict=True))


def by_key(places):
    return {(p.state, p.name_norm): p for p in places}


def test_incorporated_place_beats_cdp_with_same_name():
    places = by_key(
        build_places(
            [row("TX", "Lake City CDP", lat=1, aland=999), row("TX", "Lake City city", lat=2)]
        )
    )
    assert places[("TX", "lakecity")].lat == 2


def test_real_place_beats_alias():
    places = by_key(
        build_places(
            [
                row("TN", "Nashville-Davidson metropolitan government (balance)", lat=36.1),
                row("TN", "Nashville town", lat=1.0),
            ]
        )
    )
    assert places[("TN", "nashville")].lat == 1.0
    assert ("TN", "nashvilledavidson") in places


def test_alias_resolves_when_no_real_place_exists():
    places = by_key(
        build_places([row("KY", "Louisville/Jefferson County metro government (balance)")])
    )
    assert ("KY", "louisville") in places


def test_non_conus_rows_are_skipped():
    assert (
        build_places([row("PR", "Adjuntas zona urbana"), row("AK", "Anchorage municipality")]) == []
    )
