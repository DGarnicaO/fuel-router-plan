from decimal import Decimal

import pytest
from django.db import connection

from fuel.corridor import METERS_PER_MILE, CorridorParams, explain_corridor, find_corridor_stations
from tests.factories import finish_stations, make_station

pytestmark = pytest.mark.django_db

# East-west route along latitude 39 (Kansas/Missouri), ~433 km. Densified like a real provider
# geometry: in EPSG:5070 a 2-point line would be a chord bowing away from the parallel.
ROUTE = [(-95.0 + i * 0.05, 39.0) for i in range(101)]
ROUTE_M = 433_000.0
PARAMS = CorridorParams(
    piece_miles=25, exit_buffer_miles=2, city_buffer_miles=8, k_per_bucket=5, range_miles=500
)


def find(params=PARAMS, strategy="min"):
    return find_corridor_stations(ROUTE, ROUTE_M, strategy, params)


def test_buffer_depends_on_location_source():
    near_exit = make_station(39.02, -94.0, ["3.00"], source="EXIT")  # ~1.4 mi off route
    far_exit = make_station(39.05, -94.0, ["3.00"], source="EXIT")  # ~3.5 mi: beyond 2 mi
    far_city = make_station(39.05, -93.0, ["3.00"], source="CITY")  # ~3.5 mi: within 8 mi
    too_far = make_station(39.20, -93.0, ["3.00"], source="CITY")  # ~13.8 mi
    make_station(39.0, -92.0, ["3.00"], source="NONE")
    finish_stations()

    ids = {s.id for s in find()}
    assert near_exit.id in ids
    assert far_city.id in ids
    assert far_exit.id not in ids
    assert too_far.id not in ids
    assert len(ids) == 2


def test_results_are_ordered_by_mile_marker_with_detour():
    east = make_station(39.02, -91.0, ["3.00"])
    west = make_station(39.02, -94.0, ["3.00"])
    finish_stations()

    result = find()
    assert [s.id for s in result] == [west.id, east.id]
    # West station is 1/5 of the way along the line.
    assert result[0].mile_marker_m == pytest.approx(ROUTE_M / 5, rel=0.02)
    # 0.02 deg of latitude ~ 2.22 km off route -> detour ~ 4.45 km round trip.
    assert result[0].detour_m == pytest.approx(4450, rel=0.05)
    assert (result[0].lat, result[0].lon) == pytest.approx((39.02, -94.0))


def test_price_strategy_min_vs_avg():
    make_station(39.0, -94.0, ["3.00", "3.50", "4.00"])
    finish_stations()

    assert find(strategy="min")[0].price == Decimal("3.00")
    assert find(strategy="avg")[0].price == Decimal("3.5")


def test_keeps_k_cheapest_per_bucket():
    # Three stations around mile 56-62, inside the 50-75 mile bucket.
    cheap = make_station(39.0, -93.75, ["2.90"])
    mid = make_station(39.0, -93.80, ["3.10"])
    make_station(39.0, -93.85, ["3.50"])
    finish_stations()

    params = CorridorParams(
        piece_miles=25, exit_buffer_miles=2, city_buffer_miles=8, k_per_bucket=2, range_miles=500
    )
    assert {s.id for s in find(params)} == {cheap.id, mid.id}


def test_station_without_current_price_is_ignored():
    make_station(39.0, -94.0, [])
    finish_stations()
    assert find() == []


def test_short_route_shorter_than_one_piece():
    station = make_station(39.0, -94.95, ["3.00"])
    finish_stations()
    short = [(-95.0, 39.0), (-94.9, 39.0)]
    result = find_corridor_stations(short, 8_700.0, "min", PARAMS)
    assert [s.id for s in result] == [station.id]
    assert result[0].mile_marker_m < 25 * METERS_PER_MILE


def test_spatial_index_is_used():
    make_station(39.0, -94.0, ["3.00"])
    finish_stations()
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL enable_seqscan = off")
    plan = explain_corridor(ROUTE, ROUTE_M, "min", PARAMS)
    index_lines = [
        line for line in plan.splitlines() if "Index" in line and "location_5070" in line
    ]
    assert index_lines, plan
