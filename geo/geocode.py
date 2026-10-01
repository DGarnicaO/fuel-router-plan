"""Request geocoding against the local City table: zero external calls (DESIGN.md §4 step 1)."""

import re
from dataclasses import dataclass

from django.conf import settings
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D

from geo.models import City
from geo.normalize import normalize_name
from geo.states import CONUS_BBOX, CONUS_STATES, US_STATES

_LATLON = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")
_CITY_STATE = re.compile(r"^\s*(?P<city>.+?)\s*,\s*(?P<state>[A-Za-z]{2})\s*$")


class InvalidLocation(Exception):
    def __init__(self, value: str, message: str) -> None:
        self.value = value
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ResolvedLocation:
    lat: float
    lon: float
    label: str

    @property
    def point(self) -> Point:
        return Point(self.lon, self.lat, srid=4326)


def resolve_location(value: str) -> ResolvedLocation:
    if match := _LATLON.match(value):
        return _resolve_coordinates(value, float(match[1]), float(match[2]))
    if match := _CITY_STATE.match(value):
        return _resolve_city(value, match["city"], match["state"].upper())
    raise InvalidLocation(value, "Expected 'City, ST' or 'lat,lon'.")


def _resolve_city(value: str, city: str, state: str) -> ResolvedLocation:
    if state not in US_STATES:
        raise InvalidLocation(value, f"'{state}' is not a US state code.")
    if state not in CONUS_STATES:
        raise InvalidLocation(value, "Only the contiguous United States is supported.")
    place = City.objects.filter(state=state, name_norm=normalize_name(city)).first()
    if place is None:
        raise InvalidLocation(value, f"Unknown city '{city}, {state}'.")
    return ResolvedLocation(lat=place.location.y, lon=place.location.x, label=str(place))


def _resolve_coordinates(value: str, lat: float, lon: float) -> ResolvedLocation:
    box = CONUS_BBOX
    if not (box["min_lat"] <= lat <= box["max_lat"] and box["min_lon"] <= lon <= box["max_lon"]):
        raise InvalidLocation(value, "Coordinates are outside the contiguous United States.")
    # The bounding box also covers parts of Canada and Mexico: require a nearby US place.
    point = Point(lon, lat, srid=4326)
    max_km = settings.FUEL_PLANNER["US_POINT_MAX_DISTANCE_KM"]
    if not City.objects.filter(location__dwithin=(point, D(km=max_km))).exists():
        raise InvalidLocation(value, "Coordinates are not near any US place.")
    return ResolvedLocation(lat=lat, lon=lon, label=f"{lat:.5f},{lon:.5f}")
