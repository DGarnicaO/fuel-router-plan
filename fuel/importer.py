"""Fuel price import (DESIGN.md §6). Step 1 locates stations by city centroid only;
highway-exit matching arrives in build step 4."""

import csv
import hashlib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.gis.geos import Point
from django.db import connection, transaction

from fuel.models import FuelPrice, FuelStation, PriceImport
from geo.models import City
from geo.normalize import normalize_name
from geo.states import US_STATES

COLUMNS = {
    "opis_id": "OPIS Truckstop ID",
    "name": "Truckstop Name",
    "address": "Address",
    "city": "City",
    "state": "State",
    "rack_id": "Rack ID",
    "price": "Retail Price",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fix_mojibake(text: str) -> str:
    """Repair UTF-8 text that was decoded as cp1252 upstream (e.g. "Stuckeyâ€™s" in the CSV)."""
    if "â" not in text and "Ã" not in text:
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text


@dataclass
class StationRows:
    opis_id: int
    names: Counter = field(default_factory=Counter)
    address: str = ""
    city: str = ""
    state: str = ""
    rack_id: int | None = None
    prices: list[Decimal] = field(default_factory=list)

    @property
    def name(self) -> str:
        # Most common spelling; Counter keeps first-seen order on ties.
        return self.names.most_common(1)[0][0]


@dataclass
class ParseResult:
    stations: dict[int, StationRows]
    rows_total: int = 0
    rows_non_us: int = 0
    rows_invalid: int = 0

    @property
    def rows_imported(self) -> int:
        return sum(len(s.prices) for s in self.stations.values())


def parse_rows(rows: Iterable[dict[str, str]]) -> ParseResult:
    result = ParseResult(stations={})
    for raw in rows:
        result.rows_total += 1
        row = {key: fix_mojibake((raw.get(col) or "").strip()) for key, col in COLUMNS.items()}
        state = row["state"].upper()
        if state not in US_STATES:
            result.rows_non_us += 1
            continue
        try:
            opis_id = int(row["opis_id"])
            price = Decimal(row["price"])
        except ValueError, InvalidOperation:
            result.rows_invalid += 1
            continue
        if price <= 0:
            result.rows_invalid += 1
            continue
        station = result.stations.setdefault(opis_id, StationRows(opis_id=opis_id))
        station.names[row["name"]] += 1
        station.address = station.address or row["address"]
        station.city = station.city or " ".join(row["city"].split())
        station.state = station.state or state
        if station.rack_id is None and row["rack_id"].isdigit():
            station.rack_id = int(row["rack_id"])
        station.prices.append(price)
    return result


@dataclass(frozen=True)
class ImportReport:
    price_import: PriceImport
    created: bool

    def lines(self) -> list[str]:
        pi = self.price_import
        if not self.created:
            return [
                f"File already imported on {pi.imported_at:%Y-%m-%d %H:%M} "
                f"(sha256 {pi.file_sha256[:12]}). Nothing to do."
            ]
        located = pi.stations_exit + pi.stations_city

        def pct(n: int) -> str:
            return f"{100 * n / pi.stations_total:.1f}%" if pi.stations_total else "n/a"

        return [
            f"Rows: {pi.rows_total} read, {pi.rows_imported} imported, "
            f"{pi.rows_non_us} non-US skipped, {pi.rows_invalid} invalid skipped",
            f"Stations: {pi.stations_total}",
            f"  located by exit:  {pi.stations_exit} ({pct(pi.stations_exit)})",
            f"  located by city:  {pi.stations_city} ({pct(pi.stations_city)})",
            f"  unlocated:        {pi.stations_unlocated} ({pct(pi.stations_unlocated)})",
            f"  usable for plans: {located} ({pct(located)})",
        ]


def import_prices(path: Path) -> ImportReport:
    sha = file_sha256(path)
    existing = PriceImport.objects.filter(file_sha256=sha).first()
    if existing:
        return ImportReport(existing, created=False)

    with path.open(encoding="utf-8-sig", newline="") as fh:
        parsed = parse_rows(csv.DictReader(fh))

    with transaction.atomic():
        price_import = PriceImport.objects.create(
            file_sha256=sha,
            file_name=path.name,
            rows_total=parsed.rows_total,
            rows_imported=parsed.rows_imported,
            rows_non_us=parsed.rows_non_us,
            rows_invalid=parsed.rows_invalid,
        )
        counts = _upsert_stations(parsed.stations.values())
        ids = dict(
            FuelStation.objects.filter(opis_id__in=parsed.stations).values_list("opis_id", "id")
        )
        FuelPrice.objects.bulk_create(
            (
                FuelPrice(station_id=ids[s.opis_id], price_import=price_import, price=price)
                for s in parsed.stations.values()
                for price in s.prices
            ),
            batch_size=5000,
        )
        for key, value in counts.items():
            setattr(price_import, key, value)
        price_import.save()
        refresh_effective_prices()
    return ImportReport(price_import, created=True)


def refresh_effective_prices() -> None:
    with connection.cursor() as cursor:
        cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY station_effective_price")


def _upsert_stations(stations: Iterable[StationRows]) -> dict[str, int]:
    stations = list(stations)
    centroids = {
        (state, name_norm): point
        for state, name_norm, point in City.objects.filter(
            state__in={s.state for s in stations}
        ).values_list("state", "name_norm", "location")
    }
    objs = []
    for s in stations:
        point = centroids.get((s.state, normalize_name(s.city)))
        objs.append(
            FuelStation(
                opis_id=s.opis_id,
                name=s.name,
                address=s.address,
                city=s.city,
                state=s.state,
                rack_id=s.rack_id,
                location=Point(point.x, point.y, srid=4326) if point else None,
                location_source=(
                    FuelStation.LocationSource.CITY if point else FuelStation.LocationSource.NONE
                ),
            )
        )
    FuelStation.objects.bulk_create(
        objs,
        batch_size=2000,
        update_conflicts=True,
        unique_fields=["opis_id"],
        update_fields=[
            "name",
            "address",
            "city",
            "state",
            "rack_id",
            "location",
            "location_source",
        ],
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE fuel_fuelstation SET location_5070 = ST_Transform(location::geometry, 5070) "
            "WHERE opis_id = ANY(%s)",
            [[s.opis_id for s in stations]],
        )
    by_source = Counter(o.location_source for o in objs)
    return {
        "stations_total": len(objs),
        "stations_exit": by_source[FuelStation.LocationSource.EXIT],
        "stations_city": by_source[FuelStation.LocationSource.CITY],
        "stations_unlocated": by_source[FuelStation.LocationSource.NONE],
    }
