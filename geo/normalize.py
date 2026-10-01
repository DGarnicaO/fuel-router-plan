"""City name normalization shared by the gazetteer loader, the fuel import and request geocoding.

The fuel CSV and the Census gazetteer spell places differently ("Saint Louis" vs "St. Louis city",
"Mc Calla" vs "McCalla", "Winston Salem" vs "Winston-Salem"). Both sides go through
`normalize_name`, which expands common abbreviations and then keeps only letters and digits.
"""

import re
import unicodedata

_TOKEN_ALIASES = {"st": "saint", "ste": "sainte", "mt": "mount", "ft": "fort"}

# One Census legal/statistical suffix per name ("Union City city" must keep "Union City").
_PLACE_SUFFIX = re.compile(
    r"\s+(?:city and borough|metropolitan government|metro government|unified government|"
    r"consolidated government|urban county|government|city|town|village|borough|CDP|"
    r"municipality|corporation|comunidad|zona urbana)$",
    re.IGNORECASE,
)
_BALANCE = " (balance)"


def normalize_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", ascii_name.lower())
    return "".join(_TOKEN_ALIASES.get(token, token) for token in tokens)


def place_name_variants(census_name: str) -> tuple[str, list[str]]:
    """Return (display name, extra alias names) for a Census gazetteer NAME value.

    Consolidated city-county governments ("Nashville-Davidson metropolitan government (balance)")
    also get the plain city name as an alias so "Nashville, TN" resolves.
    """
    is_balance = census_name.endswith(_BALANCE)
    name = census_name.removesuffix(_BALANCE).strip()
    name = _PLACE_SUFFIX.sub("", name, count=1).strip()
    aliases: list[str] = []
    if is_balance:
        head = re.split(r"[/-]", name, maxsplit=1)[0].strip()
        if head and head != name:
            aliases.append(head)
    return name, aliases
