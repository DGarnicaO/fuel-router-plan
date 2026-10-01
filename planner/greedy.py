"""Greedy baseline for fixed-route refueling (DESIGN.md §9).

At each node (origin or a station where we may stop):
  1. Scan ahead, in route order, through the nodes reachable on a full tank. If a strictly
     cheaper station comes first, buy just enough to reach it. If the destination comes first,
     buy just enough to arrive with the required end fuel.
  2. Otherwise fill up and go to the cheapest station within reach (farthest on ties).

The origin behaves like a station that sells nothing at price 0: we only choose where to stop
first. Optimal when detours are zero; the exact DP (build step 3) supersedes it.

Fuel bookkeeping is "on-route" fuel: the tank level while driving along the route. Stopping at
a station with detour d burns d/2 / mpg to reach the pump and the same to come back.
"""

from collections.abc import Iterable
from decimal import Decimal

from planner.models import ZERO, NoFeasiblePlan, Plan, Station, Stop, Trip, Vehicle


def plan_greedy(trip: Trip, stations: Iterable[Station], vehicle: Vehicle) -> Plan:
    for name, fraction in (("start_fuel", trip.start_fuel), ("end_fuel", trip.end_fuel)):
        if not ZERO <= fraction <= 1:
            raise ValueError(f"{name} must be between 0 and 1, got {fraction}")

    route = sorted(
        (s for s in stations if ZERO <= s.mile <= trip.distance_miles),
        key=lambda s: (s.mile, s.id),
    )
    capacity = vehicle.capacity
    end_gallons = trip.end_fuel * capacity
    half_detour = {s.id: vehicle.gallons_for(s.detour_miles) / 2 for s in route}

    stops: list[Stop] = []
    detour_gallons = ZERO
    here: Station | None = None  # None means the origin
    fuel = trip.start_fuel * capacity  # on-route fuel on arrival at `here`
    index = 0  # first station strictly after `here` in `route`

    while True:
        here_mile = here.mile if here else ZERO
        here_price = here.price if here else ZERO
        h_here = half_detour[here.id] if here else ZERO
        # On-route fuel we can leave with: a full tank minus the drive back from the pump.
        # The origin cannot sell anything.
        max_after = capacity - h_here if here else fuel

        def fuel_to_reach(station: Station, from_mile: Decimal = here_mile) -> Decimal:
            return vehicle.gallons_for(station.mile - from_mile) + half_detour[station.id]

        dest_need = vehicle.gallons_for(trip.distance_miles - here_mile) + end_gallons

        target: Decimal | None = None
        next_station: Station | None = None
        for candidate in route[index:]:
            if vehicle.gallons_for(candidate.mile - here_mile) > max_after:
                break  # stations are sorted by mile: nothing further is reachable
            if fuel_to_reach(candidate) > max_after:
                continue  # its detour is too long, but a later station may still be reachable
            if candidate.price < here_price:
                target, next_station = fuel_to_reach(candidate), candidate
                break
        if target is None and dest_need <= max_after:
            target = dest_need

        if target is None:
            # No cheaper station and no destination within reach: fill up, go to the cheapest.
            reachable = [s for s in route[index:] if fuel_to_reach(s) <= max_after]
            if not reachable:
                if index < len(route):
                    raise NoFeasiblePlan(
                        here_mile,
                        route[index].mile,
                        "Next fuel station is beyond the vehicle range",
                    )
                if dest_need - end_gallons <= max_after:
                    reason = "No station close enough to the destination to arrive with end_fuel"
                else:
                    reason = "Destination is beyond the vehicle range"
                raise NoFeasiblePlan(here_mile, trip.distance_miles, reason)
            next_station = min(reachable, key=lambda s: (s.price, -s.mile))
            target = max_after

        if here is not None and fuel < target:
            gallons = target - (fuel - 2 * h_here)
            stops.append(Stop(station=here, gallons=gallons, cost=gallons * here.price))
            detour_gallons += 2 * h_here
            fuel = target

        if next_station is None:
            break
        fuel -= vehicle.gallons_for(next_station.mile - here_mile)
        here = next_station
        index = route.index(next_station) + 1

    consumed = vehicle.gallons_for(trip.distance_miles) + detour_gallons
    return Plan(stops=tuple(stops), gallons_consumed=consumed)
