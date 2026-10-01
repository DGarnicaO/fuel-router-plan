import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from fuel.importer import fix_mojibake, import_prices
from fuel.models import FuelPrice, FuelStation, PriceImport, StationEffectivePrice
from tests.factories import make_fixture_cities

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "fuel_small.csv"


def test_fix_mojibake():
    assert fix_mojibake("Stuckeyâ€™s") == "Stuckey\N{RIGHT SINGLE QUOTATION MARK}s"
    assert fix_mojibake("Plain Name") == "Plain Name"


@pytest.mark.django_db
class TestImport:
    @pytest.fixture(autouse=True)
    def cities(self):
        make_fixture_cities()

    def test_row_accounting(self):
        report = import_prices(FIXTURE)
        pi = report.price_import
        assert report.created
        assert pi.rows_total == 10
        assert pi.rows_non_us == 1  # Edmonton, AB
        assert pi.rows_invalid == 1  # "n/a" price
        assert pi.rows_imported == 8
        assert FuelPrice.objects.count() == 8

    def test_one_station_per_opis_id_with_most_common_name(self):
        import_prices(FIXTURE)
        assert FuelStation.objects.count() == 6
        saginaw = FuelStation.objects.get(opis_id=105)
        assert saginaw.name == "TA SAGINAW I 75 TRAVEL CENTER"
        assert saginaw.prices.count() == 3

    def test_city_whitespace_is_stripped_and_names_normalized(self):
        import_prices(FIXTURE)
        assert FuelStation.objects.get(opis_id=128).city == "Effingham"
        # "Saint Louis" in the CSV matches the gazetteer's "St. Louis".
        assert FuelStation.objects.get(opis_id=2231).location_source == "CITY"

    def test_unknown_city_is_unlocated_and_reported(self):
        pi = import_prices(FIXTURE).price_import
        nowhere = FuelStation.objects.get(opis_id=9999)
        assert nowhere.location_source == "NONE"
        assert nowhere.location is None
        assert (pi.stations_city, pi.stations_unlocated) == (5, 1)

    def test_projected_location_is_filled(self):
        import_prices(FIXTURE)
        station = FuelStation.objects.get(opis_id=7)
        assert station.location_5070 is not None
        assert station.location_5070.srid == 5070

    def test_mojibake_name_is_repaired(self):
        import_prices(FIXTURE)
        assert FuelStation.objects.get(opis_id=71108).name.startswith(
            "Stuckey\N{RIGHT SINGLE QUOTATION MARK}s"
        )

    def test_materialized_view_has_min_and_avg(self):
        import_prices(FIXTURE)
        eff = StationEffectivePrice.objects.get(station__opis_id=105)
        assert eff.min_price == Decimal("3.269")
        assert eff.avg_price == pytest.approx(Decimal("3.34566667"), abs=Decimal("1e-8"))
        assert eff.n_obs == 3
        assert StationEffectivePrice.objects.count() == 6

    def test_same_file_twice_is_a_no_op(self):
        import_prices(FIXTURE)
        second = import_prices(FIXTURE)
        assert not second.created
        assert PriceImport.objects.count() == 1
        assert FuelPrice.objects.count() == 8

    def test_new_file_replaces_effective_prices(self, tmp_path):
        import_prices(FIXTURE)
        updated = tmp_path / "fuel_v2.csv"
        shutil.copy(FIXTURE, updated)
        with updated.open("a", encoding="utf-8") as fh:
            fh.write('7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,1.999\n')
        import_prices(updated)
        assert PriceImport.objects.count() == 2
        assert StationEffectivePrice.objects.get(station__opis_id=7).min_price == Decimal("1.999")

    def test_command_prints_coverage_report(self, capsys):
        call_command("load_fuel_prices", str(FIXTURE))
        out = capsys.readouterr().out
        assert "located by city:  5 (83.3%)" in out
        assert "unlocated:        1 (16.7%)" in out


@pytest.mark.django_db
def test_command_requires_cities():
    with pytest.raises(CommandError, match="load_cities"):
        call_command("load_fuel_prices", str(FIXTURE))
