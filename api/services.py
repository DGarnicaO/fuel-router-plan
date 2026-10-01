"""RoutePlanService (DESIGN.md §4): geocode, route (1 provider call), corridor SQL, optimize."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.gis.geos import LineString

from fuel.corridor import METERS_PER_MILE, CorridorParams, CorridorStation, find_corridor_stations
from geo.geocode import ResolvedLocation, resolve_location
from planner.greedy import plan_greedy
from planner.models import Plan, Station, Trip, Vehicle, to_decimal
from routing.base import LatLon, Route, RouteProvider


@dataclass(frozen=True, slots=True)
class PlanParams:
    start: str
    finish: str
    price_strategy: str
    start_fuel: Decimal
    end_fuel: Decimal
    geometry: str  # "simplified" | "full" | "none"


@dataclass(frozen=True, slots=True)
class PlannedStop:
    station: CorridorStation
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class PlanResult:
    params: PlanParams
    start: ResolvedLocation
    finish: ResolvedLocation
    route: Route
    plan: Plan
    stops: list[PlannedStop]
    geometry: dict | None
    vehicle: Vehicle
    timings_ms: dict[str, float] = field(default_factory=dict)

    @property
    def distance_miles(self) -> Decimal:
        return to_decimal(self.route.distance_m) / to_decimal(METERS_PER_MILE)

    @property
    def map_url(self) -> str:
        query = urlencode({"start": self.params.start, "finish": self.params.finish})
        return f"/route-plan/map/?{query}"


def _miles(meters: float) -> Decimal:
    return to_decimal(round(meters / METERS_PER_MILE, 6))


class RoutePlanService:
    def __init__(self, provider: RouteProvider) -> None:
        self.provider = provider
        conf = settings.FUEL_PLANNER
        self.vehicle = Vehicle(
            range_miles=to_decimal(conf["RANGE_MILES"]), mpg=to_decimal(conf["MPG"])
        )
        buffers = conf["CORRIDOR_BUFFER_MILES"]
        self.corridor_params = CorridorParams(
            piece_miles=conf["CORRIDOR_PIECE_MILES"],
            exit_buffer_miles=buffers["EXIT"],
            city_buffer_miles=buffers["CITY"],
            k_per_bucket=conf["CORRIDOR_K_PER_BUCKET"],
            range_miles=conf["RANGE_MILES"],
        )
        self.simplify_tolerance = conf["SIMPLIFY_TOLERANCE_DEG"]

    def plan(self, params: PlanParams) -> PlanResult:
        timings: dict[str, float] = {}

        with _timer(timings, "geocode"):
            start = resolve_location(params.start)
            finish = resolve_location(params.finish)

        with _timer(timings, "route"):
            route = self.provider.route(
                LatLon(start.lat, start.lon), LatLon(finish.lat, finish.lon)
            )

        with _timer(timings, "corridor"):
            candidates = find_corridor_stations(
                route.coordinates, route.distance_m, params.price_strategy, self.corridor_params
            )

        with _timer(timings, "optimize"):
            by_id = {c.id: c for c in candidates}
            plan = plan_greedy(
                Trip(
                    distance_miles=_miles(route.distance_m),
                    start_fuel=params.start_fuel,
                    end_fuel=params.end_fuel,
                ),
                [
                    Station(
                        id=c.id,
                        mile=_miles(c.mile_marker_m),
                        price=c.price,
                        detour_miles=_miles(c.detour_m),
                    )
                    for c in candidates
                ],
                self.vehicle,
            )
            stops = [
                PlannedStop(station=by_id[s.station.id], gallons=s.gallons, cost=s.cost)
                for s in plan.stops
            ]

        return PlanResult(
            params=params,
            start=start,
            finish=finish,
            route=route,
            plan=plan,
            stops=stops,
            geometry=self._geometry(route, params.geometry),
            vehicle=self.vehicle,
            timings_ms=timings,
        )

    def _geometry(self, route: Route, mode: str) -> dict | None:
        if mode == "none" or len(route.coordinates) < 2:
            return None
        coordinates = route.coordinates
        if mode == "simplified":
            line = LineString(coordinates, srid=4326).simplify(
                self.simplify_tolerance, preserve_topology=False
            )
            coordinates = [(round(x, 5), round(y, 5)) for x, y in line.coords]
        return {"type": "LineString", "coordinates": [list(c) for c in coordinates]}


@contextmanager
def _timer(timings: dict[str, float], name: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        timings[name] = (time.perf_counter() - started) * 1000
