"""Domain dataclasses for the refueling problem.

Model (DESIGN.md §9): stations sit on a line at a mile marker. Stopping at a station costs a
round-trip detour off the route; half of it is driven to reach the pump, half to come back.
Fuel quantities are Decimal gallons, money is Decimal dollars; miles are Decimal too so the
arithmetic stays exact.
"""

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal(0)


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    """Convert without importing binary float noise (Decimal(0.1) != Decimal("0.1"))."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class Vehicle:
    range_miles: Decimal
    mpg: Decimal

    @property
    def capacity(self) -> Decimal:
        return self.range_miles / self.mpg

    def gallons_for(self, miles: Decimal) -> Decimal:
        return miles / self.mpg


@dataclass(frozen=True, slots=True)
class Station:
    id: int
    mile: Decimal
    price: Decimal
    detour_miles: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class Trip:
    distance_miles: Decimal
    start_fuel: Decimal  # fraction of the tank, 0..1
    end_fuel: Decimal = ZERO  # required tank fraction on arrival, 0..1


@dataclass(frozen=True, slots=True)
class Stop:
    station: Station
    gallons: Decimal
    cost: Decimal


@dataclass(frozen=True, slots=True)
class Plan:
    stops: tuple[Stop, ...]
    gallons_consumed: Decimal

    @property
    def gallons_purchased(self) -> Decimal:
        return sum((s.gallons for s in self.stops), ZERO)

    @property
    def cost(self) -> Decimal:
        return sum((s.cost for s in self.stops), ZERO)


class NoFeasiblePlan(Exception):
    """No station sequence can cover the gap between from_mile and to_mile."""

    def __init__(self, from_mile: Decimal, to_mile: Decimal, reason: str) -> None:
        self.from_mile = from_mile
        self.to_mile = to_mile
        self.reason = reason
        super().__init__(f"{reason} (between mile {from_mile:.1f} and mile {to_mile:.1f})")
