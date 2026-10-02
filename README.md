# Fuel Route Planner

Django API that takes a start and finish location in the USA and returns the driving route, the most cost-effective fuel stops along it (500-mile range, 10 mpg), and the total money spent on fuel.

- **One routing call per request** (OpenRouteService, truck profile). Locations are resolved locally against the US Census gazetteer, with no geocoding API.
- **Corridor search in one SQL statement** (PostGIS): the route is split into ~25-mile pieces so the spatial index stays selective.
- **Optimizer in pure Python**, with `Decimal` money and no Django imports.

Design decisions and their reasoning: [DESIGN.md](DESIGN.md).

## Quick start

Requirements: Docker. An [OpenRouteService API key](https://openrouteservice.org/dev/#/signup) (free).

1. Copy `.env.example` to `.env` and set `ORS_API_KEY`.
2. Put the provided price file at `data/fuel-prices.csv`.
3. Start the stack and load the data. All commands run from the project folder on your machine; `docker compose exec web …` executes them inside the web container, so nothing else needs installing locally.

```bash
docker compose up -d --build     # PostGIS, Redis, web on http://localhost:8000
docker compose exec web python manage.py migrate
docker compose exec web python manage.py load_cities data/2025_Gaz_place_national.txt
docker compose exec web python manage.py load_fuel_prices data/fuel-prices.csv
```

With GNU Make available (Linux, macOS, WSL), `make up` and `make seed` run the same steps.

The price import prints a coverage report (stations located by city centroid / unlocated). Re-running it with the same file is a no-op; `.env` changes need `docker compose up -d` to recreate the container.

## API

`GET /api/v1/route-plan/`

| Param | Default | Notes |
|---|---|---|
| `start`, `finish` | required | `City, ST` or `lat,lon` (contiguous US) |
| `price_strategy` | `min` | `min` or `avg` of the duplicate price observations per station |
| `start_fuel` | `1.0` | Tank fraction at departure |
| `end_fuel` | `0.0` | Tank fraction required on arrival (e.g. return a rental at the same level) |
| `stop_penalty` | `10.00` | Dollar value of one stop (driver time). Avoids 1-gallon top-ups; never added to the cost. `0` = fuel cost only |
| `geometry` | `simplified` | `simplified`, `full` or `none` |

```bash
curl "http://localhost:8000/api/v1/route-plan/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA"
```

On Windows PowerShell use `curl.exe` (plain `curl` is an alias for `Invoke-WebRequest`).

```json
{
  "summary": {"distance_miles": 2811.5, "duration_hours": 65.4, "gallons_consumed": 284.12,
              "fuel_purchased_cost": "715.91", "stops": 6},
  "start": {"query": "New York, NY", "resolved": "New York, NY"},
  "finish": {"query": "Los Angeles, CA", "resolved": "Los Angeles, CA"},
  "route": {"type": "LineString", "coordinates": [[-73.93872, 40.6631], "..."]},
  "fuel_stops": [
    {"opis_id": 72445, "name": "SHEETZ #639", "city": "Youngstown", "state": "OH",
     "lat": 41.09909, "lon": -80.6459, "location_source": "CITY", "mile_marker": 399.4,
     "detour_miles": 7.6, "price_per_gallon": "3.059", "gallons": "40.32", "cost": "123.34"},
    "... 5 more"
  ],
  "assumptions": {"range_miles": 500.0, "mpg": 10.0, "price_strategy": "min",
                  "start_fuel": 1.0, "end_fuel": 0.0, "stop_penalty": "10.00"},
  "map_url": "/route-plan/map/?start=New+York%2C+NY&finish=Los+Angeles%2C+CA"
}
```

*(Real output, truncated; prices from the provided file.)* Errors share one shape: `{"error": {"code", "message", "details"}}`. Codes: `INVALID_LOCATION`, `INVALID_REQUEST` (400), `NO_FEASIBLE_PLAN` (422), `THROTTLED` (429), `PROVIDER_ERROR` (502), `PROVIDER_TIMEOUT` (504). The `Server-Timing` header breaks down geocode / route / corridor / optimize time.

## Project layout

```
config/    settings (all domain parameters live in FUEL_PLANNER), urls
api/       view, serializers, error schema, RoutePlanService
routing/   RouteProvider interface + OpenRouteService adapter
fuel/      stations, prices, materialized view, import command, corridor SQL
geo/       Census gazetteer, name normalization, request geocoding
planner/   pure-Python optimizer (no Django imports)
data/      Census Gazetteer 2025 places file (public domain)
```

## Tests

```bash
docker compose exec web pytest                # real PostGIS; the routing provider is always faked
docker compose exec web ruff check .          # lint
docker compose exec web ruff format --check . # formatting
```

(`make test` / `make lint` are shortcuts for the same.)

The suite covers the optimizer edge cases, name normalization, import idempotency, the corridor query (including that the GiST index is used), the ORS adapter's retry/error mapping, and every API error code.

## Status

| Build step (DESIGN.md §12) | |
|---|---|
| 1. Models, import, ORS adapter, corridor SQL, greedy optimizer, endpoint, tests | Done |
| 2. Route/plan caching with stampede lock, Leaflet map page (`map_url`) | Next |
| 3. Exact DP optimizer + Hypothesis property tests | Planned |
| 4. Highway-exit matching | Planned |
| 5. CI, OpenAPI docs, benchmarks | Planned |

## Data and attribution

- Fuel prices: file provided with the assessment.
- Places: [US Census Bureau Gazetteer Files](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html), public domain.
- Routing: [openrouteservice](https://openrouteservice.org/), © openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors.

## How this was built

I used Claude Code as a pair programmer. The design, scope and trade-offs are mine and are documented in DESIGN.md. `CLAUDE.md` holds the working rules the assistant followed. I reviewed and approved every commit.
