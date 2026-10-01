import pytest
from django.contrib.gis.geos import Point

from geo.geocode import InvalidLocation, resolve_location
from geo.models import City

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def cities():
    City.objects.create(
        name="St. Louis",
        name_norm="saintlouis",
        state="MO",
        location=Point(-90.2, 38.63, srid=4326),
    )
    City.objects.create(
        name="Buffalo", name_norm="buffalo", state="NY", location=Point(-78.86, 42.89, srid=4326)
    )


def test_city_state_resolves_with_normalized_name():
    loc = resolve_location("Saint Louis, mo")
    assert (loc.lat, loc.lon) == pytest.approx((38.63, -90.2))
    assert loc.label == "St. Louis, MO"


def test_lat_lon_near_a_us_place_is_accepted():
    loc = resolve_location(" 38.6 , -90.25 ")
    assert (loc.lat, loc.lon) == (38.6, -90.25)


@pytest.mark.parametrize(
    "value",
    [
        "Springfield",  # no state
        "Atlantis, ZZ",  # not a state
        "Honolulu, HI",  # outside CONUS
        "Nowhere, MO",  # unknown city
        "19.43,-99.13",  # Mexico City, outside the box
        "43.65,-79.38",  # Toronto: inside the box, but no US place within 50 km in this fixture
    ],
)
def test_invalid_locations(value):
    with pytest.raises(InvalidLocation):
        resolve_location(value)
