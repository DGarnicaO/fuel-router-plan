"""OpenRouteService adapter: one POST per route, 1 retry on timeout or 5xx, pooled client."""

import logging

import httpx
from django.conf import settings

from routing.base import LatLon, ProviderError, ProviderTimeout, Route, RouteNotFound

logger = logging.getLogger(__name__)

# ORS error codes that mean "these points cannot be routed" rather than "the service failed".
_UNROUTABLE_CODES = {2009, 2010}  # route not found, point not found


class ORSProvider:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        profile: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        conf = settings.ORS
        self.api_key = api_key if api_key is not None else conf["API_KEY"]
        self.profile = profile or conf["PROFILE"]
        self.client = client or httpx.Client(
            base_url=base_url or conf["BASE_URL"],
            timeout=timeout or conf["TIMEOUT_SECONDS"],
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )

    def route(self, start: LatLon, finish: LatLon) -> Route:
        response = self._post_with_retry(
            f"/v2/directions/{self.profile}/geojson",
            json={"coordinates": [[start.lon, start.lat], [finish.lon, finish.lat]]},
        )
        return self._parse(response)

    def _post_with_retry(self, path: str, json: dict) -> httpx.Response:
        headers = {"Authorization": self.api_key, "Accept": "application/geo+json"}
        for attempt in (1, 2):
            try:
                response = self.client.post(path, json=json, headers=headers)
            except httpx.TimeoutException as exc:
                if attempt == 2:
                    raise ProviderTimeout("Routing provider timed out") from exc
                logger.warning("ORS timeout, retrying")
                continue
            except httpx.HTTPError as exc:
                raise ProviderError(f"Routing provider unreachable: {exc}") from exc
            if response.status_code >= 500 and attempt == 1:
                logger.warning("ORS %s, retrying", response.status_code)
                continue
            return response
        raise AssertionError("unreachable")

    @staticmethod
    def _parse(response: httpx.Response) -> Route:
        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderError(f"Invalid JSON from provider ({response.status_code})") from exc

        if response.status_code != 200:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            if code in _UNROUTABLE_CODES:
                raise RouteNotFound(message)
            raise ProviderError(f"Provider error {response.status_code}: {message}")

        try:
            feature = body["features"][0]
            summary = feature["properties"]["summary"]
            coordinates = [(float(c[0]), float(c[1])) for c in feature["geometry"]["coordinates"]]
            return Route(
                coordinates=coordinates,
                distance_m=float(summary["distance"]),
                duration_s=float(summary.get("duration", 0.0)),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError("Unexpected provider response shape") from exc
