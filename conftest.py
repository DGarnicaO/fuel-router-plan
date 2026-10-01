import pytest


@pytest.fixture(autouse=True)
def _isolated_cache(settings):
    """Tests never share the dev Redis: each test gets an empty in-memory cache."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    from django.core.cache import cache

    cache.clear()
