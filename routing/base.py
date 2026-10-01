"""Routing provider contract. The rest of the app depends only on this module."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Route:
    coordinates: list[tuple[float, float]]  # GeoJSON order: (lon, lat)
    distance_m: float
    duration_s: float


class RouteProvider(Protocol):
    def route(self, start: LatLon, finish: LatLon) -> Route: ...


class RoutingError(Exception):
    """Base class for provider failures."""


class ProviderError(RoutingError):
    """The provider failed or answered with something unusable (maps to HTTP 502)."""


class ProviderTimeout(RoutingError):
    """The provider did not answer in time, even after a retry (maps to HTTP 504)."""


class RouteNotFound(RoutingError):
    """The provider cannot route between the points, e.g. a point is far from any road (400)."""
