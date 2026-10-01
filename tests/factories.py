"""Small helpers for DB-backed tests (no factory library needed)."""

import itertools
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.db import connection

from fuel.importer import refresh_effective_prices
from fuel.models import FuelPrice, FuelStation, PriceImport
from geo.models import City
from geo.normalize import normalize_name

_opis_ids = itertools.count(100_000)


def make_station(
    lat: float, lon: float, prices: list[str], source: str = "CITY", name: str = ""
) -> FuelStation:
    """Create a located station with price observations in the latest PriceImport.
    Call `finish_stations()` afterwards to refresh the materialized view."""
    price_import = PriceImport.objects.order_by("-id").first() or PriceImport.objects.create(
        file_sha256="test", file_name="test.csv"
    )
    opis_id = next(_opis_ids)
    located = source != "NONE"
    station = FuelStation.objects.create(
        opis_id=opis_id,
        name=name or f"STATION {opis_id}",
        address="I-00, EXIT 1",
        city="Testville",
        state="KS",
        location=Point(lon, lat, srid=4326) if located else None,
        location_source=source,
    )
    FuelPrice.objects.bulk_create(
        FuelPrice(station=station, price_import=price_import, price=Decimal(p)) for p in prices
    )
    return station


def finish_stations() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE fuel_fuelstation SET location_5070 = ST_Transform(location::geometry, 5070) "
            "WHERE location IS NOT NULL"
        )
    refresh_effective_prices()


def make_city(name: str, state: str, lat: float, lon: float) -> City:
    return City.objects.create(
        name=name, name_norm=normalize_name(name), state=state, location=Point(lon, lat, srid=4326)
    )


def make_fixture_cities() -> None:
    """Cities referenced by tests/fixtures/fuel_small.csv (Atlantis, TX is deliberately missing)."""
    make_city("Big Cabin", "OK", 36.54, -95.22)
    make_city("Bridgeport", "MI", 43.36, -83.88)
    make_city("Effingham", "IL", 39.12, -88.55)
    make_city("St. Louis", "MO", 38.63, -90.24)
    make_city("Anahuac", "TX", 29.77, -94.68)
