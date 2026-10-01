"""Fake RouteProvider for API tests: never touches the network, counts calls."""

from routing.base import LatLon, Route


class FakeRouteProvider:
    calls: list[tuple[LatLon, LatLon]] = []
    next_error: Exception | None = None

    def route(self, start: LatLon, finish: LatLon) -> Route:
        FakeRouteProvider.calls.append((start, finish))
        if FakeRouteProvider.next_error is not None:
            raise FakeRouteProvider.next_error
        # Densified straight line, like a real provider geometry.
        steps = 100
        coordinates = [
            (
                start.lon + (finish.lon - start.lon) * i / steps,
                start.lat + (finish.lat - start.lat) * i / steps,
            )
            for i in range(steps + 1)
        ]
        # Along latitude 39, 1 degree of longitude ~ 86.6 km.
        distance_m = abs(finish.lon - start.lon) * 86_600 + abs(finish.lat - start.lat) * 111_000
        return Route(coordinates=coordinates, distance_m=distance_m, duration_s=distance_m / 25)

    @classmethod
    def reset(cls) -> None:
        cls.calls = []
        cls.next_error = None
