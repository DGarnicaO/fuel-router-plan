"""US state codes. Routing math uses EPSG:5070 (Albers CONUS), so AK and HI are out of scope."""

# fmt: off
CONUS_STATES = frozenset({
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM",
    "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA",
    "WA", "WV", "WI", "WY",
})
# fmt: on
US_STATES = CONUS_STATES | {"AK", "HI"}

# Rough CONUS bounding box (lat, lon) used as a cheap first check for raw coordinates.
CONUS_BBOX = {"min_lat": 24.3, "max_lat": 49.5, "min_lon": -125.0, "max_lon": -66.8}
