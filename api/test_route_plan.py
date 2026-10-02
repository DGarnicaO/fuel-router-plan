from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from routing.base import ProviderError, ProviderTimeout, RouteNotFound
from routing.providers import get_route_provider
from tests.factories import finish_stations, make_city, make_station
from tests.fakes import FakeRouteProvider

pytestmark = pytest.mark.django_db

URL = "/api/v1/route-plan/"
# Westville (-95.0) to Eastville (-90.0) along latitude 39: ~433 km / ~269 miles.
TRIP = {"start": "Westville, KS", "finish": "Eastville, MO"}


@pytest.fixture(autouse=True)
def fake_provider(settings):
    settings.ROUTE_PROVIDER = "tests.fakes.FakeRouteProvider"
    get_route_provider.cache_clear()
    FakeRouteProvider.reset()
    yield FakeRouteProvider
    get_route_provider.cache_clear()


@pytest.fixture(autouse=True)
def places():
    make_city("Westville", "KS", 39.0, -95.0)
    make_city("Eastville", "MO", 39.0, -90.0)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def stations():
    """Two stations on the route: ~mile 54 at 3.20 (avg 3.60) and ~mile 161 at 2.90."""
    west = make_station(39.0, -94.0, ["3.20", "4.00"], name="WEST FUEL")
    east = make_station(39.0, -92.0, ["2.90"], name="EAST FUEL")
    finish_stations()
    return west, east


def test_trip_within_range_needs_no_stop_and_calls_provider_once(client, fake_provider):
    response = client.get(URL, TRIP)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "summary",
        "start",
        "finish",
        "route",
        "fuel_stops",
        "assumptions",
        "map_url",
    }
    assert body["summary"]["stops"] == 0
    assert body["summary"]["fuel_purchased_cost"] == "0.00"
    assert body["summary"]["distance_miles"] == pytest.approx(269.0, abs=0.5)
    assert body["start"]["resolved"] == "Westville, KS"
    assert body["assumptions"] == {
        "range_miles": 500.0,
        "mpg": 10.0,
        "price_strategy": "min",
        "start_fuel": 1.0,
        "end_fuel": 0.0,
        "stop_penalty": "10.00",
    }
    assert body["map_url"].startswith("/route-plan/map/?start=Westville")
    assert len(fake_provider.calls) == 1
    assert "route;dur=" in response["Server-Timing"]


def test_low_start_fuel_buys_at_cheapest_reachable_station(client, stations):
    _west, east = stations
    # 0.4 tank = 200 miles: both stations reachable from the start; east is cheaper.
    body = client.get(URL, {**TRIP, "start_fuel": "0.4"}).json()

    assert [s["opis_id"] for s in body["fuel_stops"]] == [east.opis_id]
    stop = body["fuel_stops"][0]
    assert stop["price_per_gallon"] == "2.900"
    assert stop["location_source"] == "CITY"
    # Total burn ~26.9 gal; 20 gal in the tank at start -> ~6.9 gal bought.
    assert Decimal(stop["gallons"]) == pytest.approx(Decimal("6.9"), abs=Decimal("0.1"))
    assert body["summary"]["fuel_purchased_cost"] == stop["cost"]


def test_price_strategy_changes_effective_price(client):
    make_station(39.0, -94.0, ["3.00", "4.00"])
    finish_stations()
    params = {**TRIP, "start_fuel": "0.2"}

    by_min = client.get(URL, {**params, "price_strategy": "min"}).json()
    by_avg = client.get(URL, {**params, "price_strategy": "avg"}).json()

    assert by_min["fuel_stops"][0]["price_per_gallon"] == "3.000"
    assert by_avg["fuel_stops"][0]["price_per_gallon"] == "3.500"
    assert Decimal(by_avg["summary"]["fuel_purchased_cost"]) > Decimal(
        by_min["summary"]["fuel_purchased_cost"]
    )


def test_stop_penalty_zero_chases_marginally_cheaper_stations(client):
    # Two stations 8 miles apart, 1 cent apart in price, both within the first leg.
    make_station(39.0, -94.9, ["3.00"])
    make_station(39.0, -94.75, ["2.99"])
    finish_stations()
    params = {**TRIP, "start_fuel": "0.02"}  # 10 miles of fuel: must stop at the first one

    pure = client.get(URL, {**params, "stop_penalty": "0"}).json()
    practical = client.get(URL, params).json()  # default $10 per stop

    assert pure["summary"]["stops"] == 2
    assert practical["summary"]["stops"] == 1
    assert practical["assumptions"]["stop_penalty"] == "10.00"
    # The penalty shapes the plan but is never added to the money spent.
    extra = Decimal(practical["summary"]["fuel_purchased_cost"]) - Decimal(
        pure["summary"]["fuel_purchased_cost"]
    )
    assert Decimal(0) <= extra < Decimal("10.00")


def test_end_fuel_buys_extra_fuel_before_arrival(client, stations):
    base = client.get(URL, {**TRIP, "start_fuel": "0.4"}).json()
    rental = client.get(URL, {**TRIP, "start_fuel": "0.4", "end_fuel": "0.4"}).json()

    bought = sum(Decimal(s["gallons"]) for s in rental["fuel_stops"])
    # Start == end: purchases equal consumption.
    assert bought == pytest.approx(
        Decimal(str(rental["summary"]["gallons_consumed"])), abs=Decimal("0.02")
    )
    assert Decimal(rental["summary"]["fuel_purchased_cost"]) > Decimal(
        base["summary"]["fuel_purchased_cost"]
    )
    assert rental["assumptions"]["end_fuel"] == 0.4


@pytest.mark.parametrize(
    ("mode", "check"),
    [
        ("none", lambda route: route is None),
        ("full", lambda route: len(route["coordinates"]) == 101),
        ("simplified", lambda route: len(route["coordinates"]) == 2),
    ],
)
def test_geometry_modes(client, mode, check):
    body = client.get(URL, {**TRIP, "geometry": mode}).json()
    assert check(body["route"])


def assert_error(response, status, code):
    assert response.status_code == status, response.content
    error = response.json()["error"]
    assert error["code"] == code
    assert set(error) == {"code", "message", "details"}
    return error


def test_unknown_city_is_invalid_location_without_provider_call(client, fake_provider):
    error = assert_error(client.get(URL, {**TRIP, "start": "Nowhere, KS"}), 400, "INVALID_LOCATION")
    assert error["details"]["value"] == "Nowhere, KS"
    assert fake_provider.calls == []


def test_missing_and_invalid_params(client):
    assert_error(client.get(URL, {"start": "Westville, KS"}), 400, "INVALID_REQUEST")
    error = assert_error(client.get(URL, {**TRIP, "start_fuel": "1.5"}), 400, "INVALID_REQUEST")
    assert "start_fuel" in error["details"]
    assert_error(client.get(URL, {**TRIP, "price_strategy": "max"}), 400, "INVALID_REQUEST")
    assert_error(client.get(URL, {**TRIP, "stop_penalty": "-1"}), 400, "INVALID_REQUEST")


def test_no_feasible_plan(client):
    error = assert_error(client.get(URL, {**TRIP, "start_fuel": "0"}), 422, "NO_FEASIBLE_PLAN")
    assert error["details"] == {"from_mile": 0.0, "to_mile": pytest.approx(269.1, abs=0.5)}


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ProviderTimeout("slow"), 504, "PROVIDER_TIMEOUT"),
        (ProviderError("boom"), 502, "PROVIDER_ERROR"),
        (RouteNotFound("no road"), 400, "INVALID_LOCATION"),
    ],
)
def test_provider_failures(client, fake_provider, exc, status, code):
    fake_provider.next_error = exc
    assert_error(client.get(URL, TRIP), status, code)


def test_throttling(client, settings):
    settings.FUEL_PLANNER = {**settings.FUEL_PLANNER, "THROTTLE_RATE": "2/min"}
    assert client.get(URL, TRIP).status_code == 200
    assert client.get(URL, TRIP).status_code == 200
    error = assert_error(client.get(URL, TRIP), 429, "THROTTLED")
    assert error["details"]["retry_after_seconds"] > 0
