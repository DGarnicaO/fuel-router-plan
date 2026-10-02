from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from rest_framework import serializers

from api.services import PlanResult


def _default(key: str):
    def get():
        value = settings.FUEL_PLANNER[key]
        return Decimal(str(value)) if isinstance(value, float) else value

    return get


class RoutePlanQuerySerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200, help_text="'City, ST' or 'lat,lon'")
    finish = serializers.CharField(max_length=200, help_text="'City, ST' or 'lat,lon'")
    price_strategy = serializers.ChoiceField(
        choices=["min", "avg"], default=_default("PRICE_STRATEGY_DEFAULT")
    )
    start_fuel = serializers.DecimalField(
        max_digits=4,
        decimal_places=3,
        min_value=Decimal(0),
        max_value=Decimal(1),
        default=_default("START_FUEL_DEFAULT"),
    )
    end_fuel = serializers.DecimalField(
        max_digits=4,
        decimal_places=3,
        min_value=Decimal(0),
        max_value=Decimal(1),
        default=_default("END_FUEL_DEFAULT"),
    )
    stop_penalty = serializers.DecimalField(
        max_digits=6,
        decimal_places=2,
        min_value=Decimal(0),
        max_value=Decimal(1000),
        default=_default("STOP_PENALTY_DEFAULT"),
        help_text="Dollar value of one stop; 0 = minimize fuel cost only",
    )
    geometry = serializers.ChoiceField(choices=["simplified", "full", "none"], default="simplified")


def _q(value: Decimal, places: str) -> str:
    """Round only at serialization (CLAUDE.md money rule)."""
    return str(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _round(value: float | Decimal, places: int) -> float:
    return round(float(value), places)


def serialize_plan(result: PlanResult) -> dict:
    params = result.params
    return {
        "summary": {
            "distance_miles": _round(result.distance_miles, 1),
            "duration_hours": _round(result.route.duration_s / 3600, 2),
            "gallons_consumed": _round(result.plan.gallons_consumed, 2),
            "fuel_purchased_cost": _q(result.plan.cost, "0.01"),
            "stops": len(result.stops),
        },
        "start": {"query": params.start, "resolved": result.start.label},
        "finish": {"query": params.finish, "resolved": result.finish.label},
        "route": result.geometry,
        "fuel_stops": [
            {
                "opis_id": stop.station.opis_id,
                "name": stop.station.name,
                "city": stop.station.city,
                "state": stop.station.state,
                "lat": _round(stop.station.lat, 5),
                "lon": _round(stop.station.lon, 5),
                "location_source": stop.station.location_source,
                "mile_marker": _round(stop.station.mile_marker_m / 1609.344, 1),
                "detour_miles": _round(stop.station.detour_m / 1609.344, 1),
                "price_per_gallon": _q(stop.station.price, "0.001"),
                "gallons": _q(stop.gallons, "0.01"),
                "cost": _q(stop.cost, "0.01"),
            }
            for stop in result.stops
        ],
        "assumptions": {
            "range_miles": float(result.vehicle.range_miles),
            "mpg": float(result.vehicle.mpg),
            "price_strategy": params.price_strategy,
            "start_fuel": float(params.start_fuel),
            "end_fuel": float(params.end_fuel),
            "stop_penalty": _q(params.stop_penalty, "0.01"),
        },
        "map_url": result.map_url,
    }
