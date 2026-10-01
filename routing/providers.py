from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string

from routing.base import RouteProvider


@cache
def get_route_provider() -> RouteProvider:
    """Process-wide provider instance (keeps the HTTP connection pool warm).

    Selected by settings.ROUTE_PROVIDER. Tests swap the setting and call `cache_clear()`.
    """
    return import_string(settings.ROUTE_PROVIDER)()
