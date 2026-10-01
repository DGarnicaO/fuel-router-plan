"""Corridor search: stations near the route, in one SQL statement (DESIGN.md §8).

A cross-country LineString's bounding box covers most of the country, so ST_DWithin against the
whole line barely uses the GiST index. Splitting the route (in EPSG:5070, meters) into ~25-mile
pieces gives each piece a tight box, so the index stays selective.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from django.db import connection

METERS_PER_MILE = 1609.344

PRICE_COLUMNS = {"min": "min_price", "avg": "avg_price"}

# Notes on the statement:
# * The first ST_DWithin uses the largest buffer, so the planner can use the GiST index on
#   location_5070 (a per-row CASE distance would not be indexable). The second one applies the
#   real buffer for each location source.
# * mile marker = fraction along the projected line x provider road distance.
# * detour = 2 x distance from the route (there and back).
# * Pruning keeps the k cheapest stations per piece-length bucket, ranked by price inflated by
#   the detour fuel spread over a full tank.
CORRIDOR_SQL = """
WITH route AS (
    SELECT ST_Transform(ST_GeomFromText(%(route_wkt)s, 4326), 5070) AS geom
),
r AS (
    SELECT geom, ST_Length(geom) AS len FROM route
),
pieces AS (
    SELECT ST_LineSubstring(
               r.geom,
               LEAST(i * %(piece_m)s / r.len, 1.0),
               LEAST((i + 1) * %(piece_m)s / r.len, 1.0)
           ) AS geom
    FROM r, generate_series(0, GREATEST(CEIL(r.len / %(piece_m)s)::int - 1, 0)) AS i
),
candidates AS (
    SELECT DISTINCT ON (s.id)
        s.id, s.opis_id, s.name, s.city, s.state, s.location_source, s.location, s.location_5070
    FROM pieces p
    JOIN fuel_fuelstation s
      ON ST_DWithin(p.geom, s.location_5070, %(max_buffer_m)s)
     AND ST_DWithin(
             p.geom,
             s.location_5070,
             CASE s.location_source
                 WHEN 'EXIT' THEN %(exit_buffer_m)s
                 ELSE %(city_buffer_m)s
             END
         )
    WHERE s.location_source <> 'NONE'
    ORDER BY s.id
),
scored AS (
    SELECT
        c.*,
        ST_LineLocatePoint(r.geom, c.location_5070) * %(route_m)s AS mile_m,
        2 * ST_Distance(r.geom, c.location_5070) AS detour_m,
        e.{price_column} AS price
    FROM candidates c
    CROSS JOIN r
    JOIN station_effective_price e ON e.station_id = c.id
),
ranked AS (
    SELECT
        scored.*,
        ROW_NUMBER() OVER (
            PARTITION BY FLOOR(mile_m / %(piece_m)s)
            ORDER BY price * (1 + detour_m / %(range_m)s), id
        ) AS rn
    FROM scored
)
SELECT
    id, opis_id, name, city, state, location_source,
    ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,
    mile_m, detour_m, price
FROM ranked
WHERE rn <= %(k)s
ORDER BY mile_m, id
"""


@dataclass(frozen=True, slots=True)
class CorridorStation:
    id: int
    opis_id: int
    name: str
    city: str
    state: str
    location_source: str
    lat: float
    lon: float
    mile_marker_m: float
    detour_m: float
    price: Decimal


@dataclass(frozen=True, slots=True)
class CorridorParams:
    piece_miles: float
    exit_buffer_miles: float
    city_buffer_miles: float
    k_per_bucket: int
    range_miles: float


def route_wkt(coordinates: Sequence[Sequence[float]]) -> str:
    """GeoJSON-order (lon, lat) coordinates to a WKT LineString."""
    return "LINESTRING(" + ", ".join(f"{lon} {lat}" for lon, lat, *_ in coordinates) + ")"


def _sql_params(
    coordinates: Sequence[Sequence[float]], route_distance_m: float, params: CorridorParams
) -> dict:
    exit_m = params.exit_buffer_miles * METERS_PER_MILE
    city_m = params.city_buffer_miles * METERS_PER_MILE
    return {
        "route_wkt": route_wkt(coordinates),
        "route_m": route_distance_m,
        "piece_m": params.piece_miles * METERS_PER_MILE,
        "exit_buffer_m": exit_m,
        "city_buffer_m": city_m,
        "max_buffer_m": max(exit_m, city_m),
        "range_m": params.range_miles * METERS_PER_MILE,
        "k": params.k_per_bucket,
    }


def corridor_sql(price_strategy: str) -> str:
    # The column name comes from a fixed whitelist, never from user input.
    return CORRIDOR_SQL.format(price_column=PRICE_COLUMNS[price_strategy])


def find_corridor_stations(
    coordinates: Sequence[Sequence[float]],
    route_distance_m: float,
    price_strategy: str,
    params: CorridorParams,
) -> list[CorridorStation]:
    with connection.cursor() as cursor:
        cursor.execute(
            corridor_sql(price_strategy), _sql_params(coordinates, route_distance_m, params)
        )
        return [CorridorStation(*row) for row in cursor.fetchall()]


def explain_corridor(
    coordinates: Sequence[Sequence[float]],
    route_distance_m: float,
    price_strategy: str,
    params: CorridorParams,
    analyze: bool = False,
) -> str:
    prefix = "EXPLAIN (ANALYZE, BUFFERS) " if analyze else "EXPLAIN "
    with connection.cursor() as cursor:
        cursor.execute(
            prefix + corridor_sql(price_strategy),
            _sql_params(coordinates, route_distance_m, params),
        )
        return "\n".join(row[0] for row in cursor.fetchall())
