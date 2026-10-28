"""US weekly stocks from the EIA open-data API (v2). No Streamlit.

Needs a free API key (https://www.eia.gov/opendata/). The key is sent as a query
parameter, so errors here never repeat the URL.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import requests

BASE = "https://api.eia.gov/v2"
TIMEOUT = 40
PAGE = 5000


class EiaError(RuntimeError):
    """Safe to show: never contains the API key."""


@dataclass(frozen=True)
class Series:
    key: str  # short name used in tables
    series_id: str
    route: str
    unit: str
    divisor: float  # API value / divisor = unit shown


SERIES: tuple[Series, ...] = (
    Series("Crude (commercial)", "WCESTUS1", "petroleum/stoc/wstk", "mb", 1000),
    Series("SPR", "WCSSTUS1", "petroleum/stoc/wstk", "mb", 1000),
    Series("Cushing crude", "W_EPC0_SAX_YCUOK_MBBL", "petroleum/stoc/wstk", "mb", 1000),
    # Total gasoline (finished motor gasoline plus blending components)
    Series("Gasoline", "WGTSTUS1", "petroleum/stoc/wstk", "mb", 1000),
    Series("Distillate", "WDISTUS1", "petroleum/stoc/wstk", "mb", 1000),
    Series("Jet fuel", "WKJSTUS1", "petroleum/stoc/wstk", "mb", 1000),
    Series("Natural gas", "NW2_EPG0_SWO_R48_BCF", "natural-gas/stor/wkly", "bcf", 1),
)
UNIT_LABEL = {"mb": "mbbls", "bcf": "Bcf"}
BY_KEY = {s.key: s for s in SERIES}


def parse(payload: dict, specs: tuple[Series, ...] = SERIES) -> pd.DataFrame:
    """API response -> rows of (period, series, value) with values in display units."""
    rows = (payload.get("response") or {}).get("data") or []
    divisor = {s.series_id: (s.key, s.divisor) for s in specs}
    out = []
    for row in rows:
        found = divisor.get(str(row.get("series")))
        if not found or row.get("value") in (None, ""):
            continue
        try:
            out.append((pd.Timestamp(row["period"]), found[0], float(row["value"]) / found[1]))
        except (ValueError, TypeError, KeyError):
            continue
    return pd.DataFrame(out, columns=["period", "series", "value"])


def _get(url: str, params: dict) -> dict:
    try:
        reply = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise EiaError(f"Could not reach api.eia.gov ({type(error).__name__}).") from None
    if reply.status_code in (400, 401, 403):
        raise EiaError("EIA rejected the request: check that EIA_API_KEY is a valid key.")
    if reply.status_code != 200:
        raise EiaError(f"EIA answered with HTTP {reply.status_code}.")
    try:
        return reply.json()
    except ValueError:
        raise EiaError("EIA returned something that is not JSON.") from None


def fetch(api_key: str, start: str = "1982-01-01", specs: tuple[Series, ...] = SERIES) -> pd.DataFrame:
    """Weekly stocks for every series since ``start`` (one request per data set)."""
    frames = []
    for route in dict.fromkeys(s.route for s in specs):
        ids = [s.series_id for s in specs if s.route == route]
        offset = 0
        while True:
            params = {
                "api_key": api_key,
                "frequency": "weekly",
                "data[0]": "value",
                "facets[series][]": ids,
                "start": start,
                "sort[0][column]": "period",
                "sort[0][direction]": "asc",
                "offset": offset,
                "length": PAGE,
            }
            payload = _get(f"{BASE}/{route}/data/", params)
            frame = parse(payload, specs)
            frames.append(frame)
            total = int((payload.get("response") or {}).get("total") or 0)
            offset += PAGE
            if offset >= total or not (payload.get("response") or {}).get("data"):
                break
    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["period", "series", "value"])
    if result.empty:
        raise EiaError("EIA returned no stock data for these series.")
    return result.drop_duplicates(["period", "series"]).sort_values(["series", "period"]).reset_index(drop=True)
