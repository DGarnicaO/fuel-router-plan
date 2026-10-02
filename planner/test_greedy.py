from decimal import Decimal as D

import pytest

from planner.greedy import plan_greedy
from planner.models import NoFeasiblePlan, Station, Trip, Vehicle

TRUCK = Vehicle(range_miles=D(500), mpg=D(10))  # 50 gallon tank


def st(id_, mile, price, detour=0):
    return Station(id=id_, mile=D(str(mile)), price=D(str(price)), detour_miles=D(str(detour)))


def trip(distance, start_fuel=1, end_fuel=0, stop_penalty=0):
    return Trip(
        distance_miles=D(str(distance)),
        start_fuel=D(str(start_fuel)),
        end_fuel=D(str(end_fuel)),
        stop_penalty=D(str(stop_penalty)),
    )


def summary(plan):
    return [(s.station.id, s.gallons, s.cost) for s in plan.stops]


def test_no_stop_when_tank_covers_trip():
    plan = plan_greedy(trip(300), [st(1, 100, "3.00")], TRUCK)
    assert plan.stops == ()
    assert plan.cost == D(0)
    assert plan.gallons_consumed == D(30)


def test_exactly_500_miles_needs_no_stop():
    assert plan_greedy(trip(500), [], TRUCK).stops == ()


def test_just_over_500_miles_without_stations_is_infeasible():
    with pytest.raises(NoFeasiblePlan) as exc:
        plan_greedy(trip("500.1"), [], TRUCK)
    assert exc.value.from_mile == D(0)
    assert exc.value.to_mile == D("500.1")


def test_drives_to_cheapest_reachable_and_buys_only_what_is_needed():
    stations = [st(1, 100, "3.00"), st(2, 400, "2.50")]
    plan = plan_greedy(trip(600), stations, TRUCK)
    # Arrive at mile 400 with 10 gal, need 20 gal for the last 200 miles.
    assert summary(plan) == [(2, D(10), D("25.00"))]


def test_partial_fill_when_cheaper_station_is_ahead():
    stations = [st(1, 400, "3.50"), st(2, 700, "3.00")]
    plan = plan_greedy(trip(900), stations, TRUCK)
    # At mile 400 buy just enough to reach the cheaper station at 700, then finish from there.
    assert summary(plan) == [(1, D(20), D("70.00")), (2, D(20), D("60.00"))]
    assert plan.cost == D("130.00")


def test_fills_up_when_no_cheaper_station_is_within_reach():
    stations = [st(1, 450, "2.00"), st(2, 900, "3.00")]
    plan = plan_greedy(trip(1200), stations, TRUCK)
    assert summary(plan) == [(1, D(45), D("90.00")), (2, D(25), D("75.00"))]
    assert plan.cost == D("165.00")


def test_gap_longer_than_range_is_infeasible_with_location():
    stations = [st(1, 100, "3.00"), st(2, 700, "3.00")]
    with pytest.raises(NoFeasiblePlan) as exc:
        plan_greedy(trip(1200), stations, TRUCK)
    assert (exc.value.from_mile, exc.value.to_mile) == (D(100), D(700))


def test_empty_start_tank_requires_station_at_origin():
    plan = plan_greedy(trip(200, start_fuel=0), [st(1, 0, "3.00")], TRUCK)
    assert summary(plan) == [(1, D(20), D("60.00"))]

    with pytest.raises(NoFeasiblePlan):
        plan_greedy(trip(200, start_fuel=0), [st(1, 5, "3.00")], TRUCK)


def test_half_tank_start():
    plan = plan_greedy(trip(400, start_fuel="0.5"), [st(1, 200, "3.00")], TRUCK)
    # 25 gal at start, 5 left at mile 200, 20 needed for the rest.
    assert summary(plan) == [(1, D(15), D("45.00"))]


def test_detour_fuel_is_bought_and_counted():
    # 10-mile round trip off the route: 0.5 gal to reach the pump, 0.5 gal to come back.
    plan = plan_greedy(trip(600), [st(1, 400, "3.00", detour=10)], TRUCK)
    assert summary(plan) == [(1, D(11), D("33.00"))]
    assert plan.gallons_consumed == D(61)
    # Mass balance: start tank + purchases == consumption + end tank.
    assert D(50) + plan.gallons_purchased == plan.gallons_consumed + D(0)


def test_no_detour_charged_when_station_is_passed_without_buying():
    # Station 1 is reachable but the tank already covers the trip: no stop, no detour fuel.
    plan = plan_greedy(trip(450), [st(1, 100, "1.00", detour=10)], TRUCK)
    assert plan.stops == ()
    assert plan.gallons_consumed == D(45)


def test_end_fuel_is_bought_at_the_best_station_before_arrival():
    plan = plan_greedy(trip(600, end_fuel="0.2"), [st(1, 450, "3.00")], TRUCK)
    # Arrive at 450 with 5 gal; need 15 gal to finish + 10 gal left in the tank.
    assert summary(plan) == [(1, D(20), D("60.00"))]


def test_end_fuel_equal_to_start_fuel_makes_purchases_equal_consumption():
    stations = [st(1, 300, "3.00"), st(2, 590, "3.10")]
    plan = plan_greedy(trip(600, start_fuel="0.8", end_fuel="0.8"), stations, TRUCK)
    assert plan.gallons_purchased == plan.gallons_consumed


def test_full_end_tank_without_station_at_destination_is_infeasible():
    with pytest.raises(NoFeasiblePlan) as exc:
        plan_greedy(trip(300, end_fuel=1), [st(1, 250, "3.00")], TRUCK)
    assert exc.value.to_mile == D(300)


MICRO_STOP_ROUTE = [st(1, 0, "3.00"), st(2, 10, "2.99"), st(3, 450, "3.50")]


def test_without_stop_penalty_greedy_chases_a_one_cent_cheaper_station():
    plan = plan_greedy(trip(600, start_fuel=0), MICRO_STOP_ROUTE, TRUCK)
    # Buys 1 gal at A just to reach B (1 cent cheaper) 10 miles later.
    assert summary(plan) == [
        (1, D(1), D("3.00")),
        (2, D(50), D("149.50")),
        (3, D(9), D("31.50")),
    ]


def test_stop_penalty_skips_stops_that_do_not_pay_for_themselves():
    plan = plan_greedy(trip(600, start_fuel=0, stop_penalty=10), MICRO_STOP_ROUTE, TRUCK)
    # B saves 1 cent/gal, far below $10 / 50 gal = 20 cents: fill at A, next stop C.
    assert summary(plan) == [(1, D(50), D("150.00")), (3, D(10), D("35.00"))]
    # One stop fewer for $1 more fuel: worth it at a $10 stop cost.
    assert plan.cost == D("185.00")


def test_stop_penalty_still_takes_a_much_cheaper_station():
    stations = [st(1, 0, "3.50"), st(2, 100, "2.90"), st(3, 450, "3.50")]
    plan = plan_greedy(trip(600, start_fuel=0, stop_penalty=10), stations, TRUCK)
    # 60 cents/gal cheaper is well above the 20 cent threshold: buy just enough to reach it.
    assert summary(plan)[0] == (1, D(10), D("35.00"))
    assert summary(plan)[1][0] == 2


def test_negative_stop_penalty_is_rejected():
    with pytest.raises(ValueError):
        plan_greedy(trip(100, stop_penalty=-1), [], TRUCK)


def test_input_order_does_not_matter():
    stations = [st(2, 700, "3.00"), st(1, 400, "3.50")]
    assert plan_greedy(trip(900), stations, TRUCK).cost == D("130.00")


def test_rejects_fractions_outside_zero_one():
    with pytest.raises(ValueError):
        plan_greedy(trip(100, start_fuel="1.5"), [], TRUCK)
