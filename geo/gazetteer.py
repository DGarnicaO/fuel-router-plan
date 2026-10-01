"""Parse the Census Gazetteer "places" file into City rows (one per state + normalized name)."""

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from geo.normalize import normalize_name, place_name_variants
from geo.states import CONUS_STATES


@dataclass(frozen=True, slots=True)
class GazetteerPlace:
    name: str
    name_norm: str
    state: str
    lat: float
    lon: float


def read_gazetteer(path: Path) -> Iterator[dict[str, str]]:
    """Yield raw rows. Recent files are pipe-delimited; older ones are tab-delimited."""
    with path.open(encoding="utf-8", newline="") as fh:
        delimiter = "|" if "|" in fh.readline() else "\t"
        fh.seek(0)
        reader = csv.DictReader(fh, delimiter=delimiter)
        for row in reader:
            yield {key.strip(): (value or "").strip() for key, value in row.items() if key}


def build_places(rows: Iterable[dict[str, str]]) -> list[GazetteerPlace]:
    """Deduplicate on (state, name_norm). Preference: real name over alias, incorporated place
    over CDP, then larger land area."""
    best: dict[tuple[str, str], tuple[tuple, GazetteerPlace]] = {}
    for row in rows:
        state = row["USPS"]
        if state not in CONUS_STATES:
            continue
        display, aliases = place_name_variants(row["NAME"])
        lat, lon = float(row["INTPTLAT"]), float(row["INTPTLONG"])
        is_cdp = row["NAME"].endswith(" CDP")
        land = int(row.get("ALAND") or 0)
        for is_alias, name in [(False, display), *((True, a) for a in aliases)]:
            norm = normalize_name(name)
            if not norm:
                continue
            rank = (is_alias, is_cdp, -land)
            key = (state, norm)
            if key not in best or rank < best[key][0]:
                best[key] = (rank, GazetteerPlace(name, norm, state, lat, lon))
    return [place for _, place in best.values()]
