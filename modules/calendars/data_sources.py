"""Calendar data for the home page: public holidays and contract expiries. No Streamlit.

Holidays come from the ``holidays`` package. Expiries are ICE's published last trading
days, kept in ``data/expiries.json`` (copied from ICE's expiry pages; add contracts there).
"""

from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

EXPIRIES = Path(__file__).parent / "data" / "expiries.json"

# name shown -> holidays-package country code
COUNTRIES = {"US": "US", "UK": "GB", "Singapore": "SG", "China": "CN"}


def holidays_between(start: dt.date, end: dt.date, countries: list[str]) -> pd.DataFrame:
    """Public holidays from ``start`` to ``end`` (inclusive): Date, Country, Holiday."""
    import holidays

    years = list(range(start.year, end.year + 1))
    rows = []
    for name in countries:
        code = COUNTRIES[name]
        subdiv = "ENG" if code == "GB" else None
        try:  # English names (China's default is Chinese)
            calendar = holidays.country_holidays(code, years=years, subdiv=subdiv, language="en_US")
        except (NotImplementedError, ValueError, TypeError):
            calendar = holidays.country_holidays(code, years=years, subdiv=subdiv)
        rows += [(day, name, label) for day, label in calendar.items() if start <= day <= end]
    frame = pd.DataFrame(rows, columns=["Date", "Country", "Holiday"])
    return frame.sort_values(["Date", "Country"]).reset_index(drop=True)


@lru_cache(maxsize=1)
def _expiry_data() -> dict:
    return json.loads(EXPIRIES.read_text(encoding="utf-8"))


def expiry_products() -> list[str]:
    return list(_expiry_data()["contracts"])


def expiry_source(product: str) -> str:
    return _expiry_data()["contracts"][product].get("source", "")


def expiries_between(start: dt.date, end: dt.date, products: list[str]) -> pd.DataFrame:
    """Last trading days from ``start`` to ``end``: Date, Product, Contract."""
    rows = []
    contracts = _expiry_data()["contracts"]
    for product in products:
        for contract, day in contracts[product]["dates"].items():
            date = dt.date.fromisoformat(day)
            if start <= date <= end:
                rows.append((date, product, contract))
    frame = pd.DataFrame(rows, columns=["Date", "Product", "Contract"])
    return frame.sort_values(["Date", "Product"]).reset_index(drop=True)


def last_listed(product: str) -> dt.date:
    """The furthest expiry held for a product (beyond it, the file needs topping up)."""
    return max(dt.date.fromisoformat(d) for d in _expiry_data()["contracts"][product]["dates"].values())
