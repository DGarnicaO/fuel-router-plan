# Fuel Route Planner

Django API that takes a start and finish location in the USA and returns the driving route, the most cost-effective fuel stops along it (500-mile range, 10 mpg), and the total money spent on fuel.

- **One routing call per request** (OpenRouteService, truck profile). Locations are resolved locally against the US Census gazetteer, with no geocoding API.
- **Corridor search in one SQL statement** (PostGIS): the route is split into ~25-mile pieces so the spatial index stays selective.
- **Optimizer in pure Python**, with `Decimal` money and no Django imports.

Design decisions and their reasoning: [DESIGN.md](DESIGN.md).

## Quick start

Requirements: Docker. An [OpenRouteService API key](https://openrouteservice.org/dev/#/signup) (free).

```bash
cp .env.example .env                       # set ORS_API_KEY
# put the provided price file at data/fuel-prices.csv
docker compose up -d --build               # PostGIS, Redis, web on :8000
make seed                                  # migrate + load cities + import prices
```

`make seed` prints an import coverage report (stations located by city centroid / unlocated).

## API

`GET /api/v1/route-plan/`

| Param | Default | Notes |
|---|---|---|
| `start`, `finish` | required | `City, ST` or `lat,lon` (contiguous US) |
| `price_strategy` | `min` | `min` or `avg` of the duplicate price observations per station |
| `start_fuel` | `1.0` | Tank fraction at departure |
| `end_fuel` | `0.0` | Tank fraction required on arrival (e.g. return a rental at the same level) |
| `geometry` | `simplified` | `simplified`, `full` or `none` |

```bash
curl "http://localhost:8000/api/v1/route-plan/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA"
```

```json
{
  "summary": {"distance_miles": 2789.4, "duration_hours": 45.1, "gallons_consumed": 279.1,
              "fuel_purchased_cost": "812.45", "stops": 5},
  "start": {"query": "New York, NY", "resolved": "New York, NY"},
  "finish": {"query": "Los Angeles, CA", "resolved": "Los Angeles, CA"},
  "route": {"type": "LineString", "coordinates": [[-74.006, 40.7128], "..."]},
  "fuel_stops": [
    {"opis_id": 1234, "name": "...", "city": "...", "state": "PA", "lat": 40.1, "lon": -77.2,
     "location_source": "CITY", "mile_marker": 480.2, "detour_miles": 3.1,
     "price_per_gallon": "3.459", "gallons": "48.20", "cost": "166.72"}
  ],
  "assumptions": {"range_miles": 500.0, "mpg": 10.0, "price_strategy": "min",
                  "start_fuel": 1.0, "end_fuel": 0.0},
  "map_url": "/route-plan/map/?start=New+York%2C+NY&finish=Los+Angeles%2C+CA"
}
```

*(Illustrative values.)* Errors share one shape: `{"error": {"code", "message", "details"}}`. Codes: `INVALID_LOCATION`, `INVALID_REQUEST` (400), `NO_FEASIBLE_PLAN` (422), `THROTTLED` (429), `PROVIDER_ERROR` (502), `PROVIDER_TIMEOUT` (504). The `Server-Timing` header breaks down geocode / route / corridor / optimize time.

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
make test        # pytest against real PostGIS; the routing provider is always faked
make lint        # ruff
```

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
