"""Django settings. Everything environment-specific comes from env vars (see .env.example)."""

import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(int(default))).lower() in {"1", "true", "yes"}


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = env_bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "geo",
    "fuel",
    "routing",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

_db = urlparse(os.environ.get("DATABASE_URL", "postgres://fuel:fuel@localhost:5432/fuel"))
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": _db.path.lstrip("/"),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": _db.port or 5432,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

_redis_url = os.environ.get("REDIS_URL")
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": _redis_url}
        if _redis_url
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "api.errors.exception_handler",
}

# Routing provider: dotted path to a RouteProvider implementation.
ROUTE_PROVIDER = "routing.ors.ORSProvider"
ORS = {
    "API_KEY": os.environ.get("ORS_API_KEY", ""),
    "BASE_URL": "https://api.openrouteservice.org",
    "PROFILE": "driving-hgv",
    "TIMEOUT_SECONDS": 5.0,
}

# Domain parameters. Request params override the *_DEFAULT values.
FUEL_PLANNER = {
    "RANGE_MILES": 500,
    "MPG": 10,
    "PRICE_STRATEGY_DEFAULT": "min",
    "START_FUEL_DEFAULT": 1.0,
    "END_FUEL_DEFAULT": 0.0,
    # Corridor search (see DESIGN.md §8).
    "CORRIDOR_PIECE_MILES": 25,
    "CORRIDOR_BUFFER_MILES": {"EXIT": 2, "CITY": 8},
    "CORRIDOR_K_PER_BUCKET": 5,
    # Geometry simplification tolerance in degrees (~100 m).
    "SIMPLIFY_TOLERANCE_DEG": 0.001,
    # A lat,lon input must have a gazetteer place within this distance to count as "in the US".
    "US_POINT_MAX_DISTANCE_KM": 50,
    "THROTTLE_RATE": "60/min",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
