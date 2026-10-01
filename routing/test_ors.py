import httpx
import pytest

from routing.base import LatLon, ProviderError, ProviderTimeout, RouteNotFound
from routing.ors import ORSProvider

START = LatLon(lat=39.10, lon=-94.58)
FINISH = LatLon(lat=38.63, lon=-90.20)

OK_BODY = {
    "type": "FeatureCollection",
    "features": [
        {
            "geometry": {"type": "LineString", "coordinates": [[-94.58, 39.10], [-90.20, 38.63]]},
            "properties": {"summary": {"distance": 400_000.0, "duration": 14_400.0}},
        }
    ],
}


def provider(handler):
    client = httpx.Client(base_url="https://ors.test", transport=httpx.MockTransport(handler))
    return ORSProvider(api_key="secret", profile="driving-hgv", client=client)


def test_success_and_request_shape():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=OK_BODY)

    route = provider(handler).route(START, FINISH)

    assert route.distance_m == 400_000.0
    assert route.duration_s == 14_400.0
    assert route.coordinates == [(-94.58, 39.10), (-90.20, 38.63)]
    assert len(seen) == 1
    request = seen[0]
    assert request.url.path == "/v2/directions/driving-hgv/geojson"
    assert request.headers["Authorization"] == "secret"
    assert request.read() == b'{"coordinates":[[-94.58,39.1],[-90.2,38.63]]}'


def test_retries_once_on_5xx_then_succeeds():
    responses = iter([httpx.Response(503, json={}), httpx.Response(200, json=OK_BODY)])
    calls = []

    def handler(request):
        calls.append(request)
        return next(responses)

    provider(handler).route(START, FINISH)
    assert len(calls) == 2


def test_second_5xx_is_provider_error():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(502, json={"error": "bad gateway"})

    with pytest.raises(ProviderError):
        provider(handler).route(START, FINISH)
    assert len(calls) == 2


def test_two_timeouts_raise_provider_timeout():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTimeout):
        provider(handler).route(START, FINISH)
    assert len(calls) == 2


def test_unroutable_point_is_route_not_found():
    body = {"error": {"code": 2010, "message": "Could not find routable point"}}

    with pytest.raises(RouteNotFound):
        provider(lambda r: httpx.Response(404, json=body)).route(START, FINISH)


def test_4xx_is_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={"error": "Access to this API has been disallowed"})

    with pytest.raises(ProviderError):
        provider(handler).route(START, FINISH)
    assert len(calls) == 1


def test_unexpected_body_is_provider_error():
    with pytest.raises(ProviderError):
        provider(lambda r: httpx.Response(200, json={"features": []})).route(START, FINISH)
