"""CFTC Commitments of Traders source.

Talks to the CFTC Public Reporting Environment (Socrata / SODA) and returns
tidy pandas frames. Nothing here imports Streamlit — caching lives in
``services.py`` so this module stays reusable (scripts, notebooks, the future
prices / EIA pipeline).

The Socrata column names for the COT datasets are inconsistent (``_all``
suffixes come and go, and the swap-dealer short leg is literally
``swap__positions_short_all`` with a double underscore). Rather than hard-code
them, we read the column list from the dataset once and resolve each field by
pattern.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import time
from dataclasses import dataclass

import pandas as pd
import requests

from modules.cftc.config import settings

BASE_URL = f"https://{settings.SODA_DOMAIN}/resource"

_EXCLUDE_TOKENS = ("change_", "pct_", "conc_", "traders_", "_ratio")
_EXCLUDE_SUFFIXES = ("_old", "_other")


class CftcDataError(RuntimeError):
    """Raised when the CFTC API cannot be reached or returns nothing usable."""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _session() -> requests.Session:
    session = requests.Session()
    token = os.getenv("SODA_APP_TOKEN")
    if token:
        # Optional: lifts the anonymous rate limit. Not required.
        session.headers["X-App-Token"] = token
    session.headers["User-Agent"] = "petroleum-cot-dashboard/0.1"
    return session


_SESSION = _session()


def _get(dataset_id: str, params: dict, retries: int = 3) -> list[dict]:
    url = f"{BASE_URL}/{dataset_id}.json"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = _SESSION.get(url, params=params, timeout=settings.REQUEST_TIMEOUT)
            if response.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:  # noqa: PERF203
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise CftcDataError(
        f"Could not read dataset {dataset_id} from {settings.SODA_DOMAIN}. "
        f"Last error: {last_error}"
    )


def dataset_id(report: str, basis: str) -> str:
    try:
        return settings.DATASETS[(report, basis)]
    except KeyError as exc:  # pragma: no cover - guarded by the UI
        raise CftcDataError(f"No dataset configured for {report}/{basis}.") from exc


# --------------------------------------------------------------------------
# Column resolution
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ColumnMap:
    date: str
    market: str
    code: str
    open_interest: str
    contract_name: str | None
    commodity: str | None
    subgroup: str | None
    group: str | None
    exchange: str | None
    sides: dict[str, dict[str, str | None]]

    def select_fields(self) -> list[str]:
        fields = [self.date, self.market, self.code, self.open_interest]
        fields += [
            col
            for col in (
                self.contract_name,
                self.commodity,
                self.subgroup,
                self.group,
                self.exchange,
            )
            if col
        ]
        for legs in self.sides.values():
            fields += [col for col in legs.values() if col]
        # de-duplicate, keep order
        return list(dict.fromkeys(fields))


def _first_present(available: list[str], candidates: list[str]) -> str | None:
    lookup = {col.lower(): col for col in available}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return None


def _match_side(available: list[str], prefix: str, side: str) -> str | None:
    pattern = re.compile(rf"^{prefix}_{side}", re.IGNORECASE)
    hits = [
        col
        for col in available
        if pattern.match(col)
        and not col.lower().endswith(_EXCLUDE_SUFFIXES)
        and not any(token in col.lower() for token in _EXCLUDE_TOKENS)
    ]
    if not hits:
        return None
    # Prefer the "_all" (all crop years / all contracts) variant, then the
    # plainest name.
    hits.sort(key=lambda col: (0 if col.lower().endswith("_all") else 1, len(col)))
    return hits[0]


def list_columns(dataset_id_: str) -> list[str]:
    rows = _get(dataset_id_, {"$limit": 1})
    if not rows:
        raise CftcDataError(f"Dataset {dataset_id_} returned no rows.")
    return list(rows[0].keys())


def resolve_columns(dataset_id_: str, report: str) -> ColumnMap:
    available = list_columns(dataset_id_)

    date = _first_present(
        available,
        ["report_date_as_yyyy_mm_dd", "report_date_as_yyyy_mm_dd_", "report_date"],
    )
    market = _first_present(
        available, ["market_and_exchange_names", "market_and_exchange_name"]
    )
    code = _first_present(
        available, ["cftc_contract_market_code", "cftc_contract_market_code_quotes"]
    )
    open_interest = _first_present(
        available, ["open_interest_all", "open_interest", "oi_all"]
    )
    if not all([date, market, code, open_interest]):
        raise CftcDataError(
            "The CFTC dataset layout changed — could not find the report date, "
            "market name, contract code or open interest columns."
        )

    sides: dict[str, dict[str, str | None]] = {}
    for category in settings.categories_for(report):
        legs = {
            "long": _match_side(available, category.prefix, "long"),
            "short": _match_side(available, category.prefix, "short"),
            "spread": (
                _match_side(available, category.prefix, "spread")
                if category.has_spread
                else None
            ),
        }
        if legs["long"] and legs["short"]:
            sides[category.key] = legs

    if not sides:
        raise CftcDataError("No trader-category columns found in the CFTC dataset.")

    return ColumnMap(
        date=date,
        market=market,
        code=code,
        open_interest=open_interest,
        contract_name=_first_present(available, ["contract_market_name"]),
        commodity=_first_present(available, ["commodity_name", "commodity"]),
        subgroup=_first_present(available, ["commodity_subgroup_name"]),
        group=_first_present(available, ["commodity_group_name"]),
        exchange=_first_present(
            available, ["cftc_market_code", "market_code", "cftc_market_code_quotes"]
        ),
        sides=sides,
    )


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------
def _title(text: str) -> str:
    """Title-case a CFTC contract name but keep trading acronyms upper case."""
    acronyms = set(settings.ACRONYMS)
    words = re.split(r"(\s+|,|/|-|\(|\))", text.strip().lower())
    out = []
    for word in words:
        bare = word.strip().upper()
        out.append(bare if bare in acronyms else word.capitalize() if word.strip() else word)
    return re.sub(r"\s{2,}", " ", "".join(out)).strip()


def pretty_name(market_name: str, contract_name: str | None, exchange: str | None) -> str:
    """Label from the CFTC's own contract name (never a coarse alias).

    Two different contracts therefore get different labels. The exchange and, as
    a last resort, the contract code are only added by ``_disambiguate`` when
    two contracts really do share a name.
    """
    upper = str(market_name or "").upper()
    for pattern, label in settings.PRODUCT_NAME_RULES:
        if re.search(pattern, upper):
            return label
    full = settings.contract_part(market_name).upper()
    if full in settings.PRODUCT_NAME_OVERRIDES:
        return settings.PRODUCT_NAME_OVERRIDES[full]
    base = (contract_name or "").strip() or settings.contract_part(market_name)
    if base.upper() in settings.PRODUCT_NAME_OVERRIDES:
        return settings.PRODUCT_NAME_OVERRIDES[base.upper()]
    return _title(base) or str(market_name)


def _disambiguate(frame: pd.DataFrame) -> pd.DataFrame:
    """Make product labels unique.

    Only needed when two contracts share a name (the same product on two
    exchanges, say). Exchange goes first; the contract code is a last resort.
    """
    frame = frame.copy()
    duplicated = frame["product"].duplicated(keep=False)
    if duplicated.any():
        exchange = frame["exchange"].fillna("").astype(str)
        add = duplicated & exchange.ne("")
        frame.loc[add, "product"] = frame.loc[add, "product"] + " (" + exchange[add] + ")"
    still = frame["product"].duplicated(keep=False)
    if still.any():
        frame.loc[still, "product"] = (
            frame.loc[still, "product"] + " [" + frame.loc[still, "contract_code"] + "]"
        )
    return frame


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------
def latest_report_date(dataset_id_: str, columns: ColumnMap) -> dt.date:
    rows = _get(dataset_id_, {"$select": f"max({columns.date}) AS latest"})
    value = rows[0].get("latest") if rows else None
    if not value:
        raise CftcDataError("The CFTC dataset did not return a latest report date.")
    return pd.to_datetime(value).date()


def _petroleum_where(columns: ColumnMap) -> str:
    """Petroleum subgroup, plus oil-named contracts filed under other subgroups."""
    name_col = columns.market
    keywords = " OR ".join(
        f"upper({name_col}) like '%{kw}%'" for kw in settings.SWEEP_KEYWORDS
    )
    if not columns.subgroup:
        return f"({keywords})"
    excluded = ", ".join(f"'{s.upper()}'" for s in settings.SWEEP_EXCLUDED_SUBGROUPS)
    return (
        f"(upper({columns.subgroup}) = '{settings.PETROLEUM_SUBGROUP}' "
        f"OR (({keywords}) AND upper({columns.subgroup}) NOT IN ({excluded})))"
    )


def fetch_contracts(dataset_id_: str, columns: ColumnMap) -> pd.DataFrame:
    """One row per petroleum contract that reported in the last few weeks.

    Looking back over a window (not just the latest date) keeps a contract in
    the filter even if it skipped a single week, and ``last_report`` shows when
    it last printed. ``source`` says how it got in: the CFTC's petroleum
    subgroup, or the oil-keyword sweep over other subgroups.
    """
    as_of = latest_report_date(dataset_id_, columns)
    since = as_of - dt.timedelta(weeks=settings.CONTRACT_LOOKBACK_WEEKS)

    wanted = [
        columns.date,
        columns.code,
        columns.market,
        columns.open_interest,
    ] + [c for c in (columns.contract_name, columns.exchange, columns.subgroup) if c]
    params = {
        "$select": ", ".join(dict.fromkeys(wanted)),
        "$where": (
            f"{columns.date} >= '{since.isoformat()}T00:00:00.000' "
            f"AND {_petroleum_where(columns)}"
        ),
        "$order": f"{columns.date} DESC",
        "$limit": settings.PAGE_SIZE,
    }
    rows = _get(dataset_id_, params)
    if not rows:
        raise CftcDataError(
            f"No petroleum contracts found in the 8 weeks to {as_of:%d %b %Y}."
        )

    frame = pd.DataFrame(rows).rename(
        columns={
            columns.date: "last_report",
            columns.code: "contract_code",
            columns.market: "market_name",
            columns.open_interest: "open_interest",
            **({columns.contract_name: "contract_name"} if columns.contract_name else {}),
            **({columns.exchange: "exchange"} if columns.exchange else {}),
            **({columns.subgroup: "subgroup"} if columns.subgroup else {}),
        }
    )
    for optional in ("contract_name", "exchange", "subgroup"):
        if optional not in frame:
            frame[optional] = None

    frame["last_report"] = pd.to_datetime(frame["last_report"]).dt.normalize()
    frame["open_interest"] = pd.to_numeric(frame["open_interest"], errors="coerce")
    frame["exchange"] = frame["exchange"].astype("string").str.strip()
    frame["contract_code"] = frame["contract_code"].astype(str).str.strip()

    # Newest print per contract.
    frame = (
        frame.sort_values("last_report", ascending=False)
        .drop_duplicates("contract_code", keep="first")
        .reset_index(drop=True)
    )
    frame["product"] = [
        pretty_name(row.market_name, row.contract_name, row.exchange)
        for row in frame.itertuples()
    ]
    frame = _disambiguate(frame)
    frame["group"] = [
        settings.classify_product(row.market_name, row.contract_code)
        for row in frame.itertuples()
    ]
    frame["source"] = [
        "CFTC petroleum subgroup"
        if str(sub).upper() == settings.PETROLEUM_SUBGROUP
        else f"Oil-name match in {sub}"
        for sub in frame["subgroup"].fillna("unknown")
    ]
    frame["as_of"] = as_of
    return frame.sort_values("open_interest", ascending=False).reset_index(drop=True)


def fetch_positions(
    dataset_id_: str,
    columns: ColumnMap,
    contract_codes: list[str],
    start_date: dt.date | None = None,
) -> pd.DataFrame:
    """Weekly history for the given contracts, tidy: one row per date × category."""
    if not contract_codes:
        return pd.DataFrame()

    quoted = ", ".join(f"'{code}'" for code in contract_codes)
    where = f"{columns.code} in ({quoted})"
    if start_date:
        where += f" AND {columns.date} >= '{start_date.isoformat()}T00:00:00.000'"

    rows: list[dict] = []
    offset = 0
    while True:
        page = _get(
            dataset_id_,
            {
                "$select": ", ".join(columns.select_fields()),
                "$where": where,
                "$order": f"{columns.date} ASC",
                "$limit": settings.PAGE_SIZE,
                "$offset": offset,
            },
        )
        rows.extend(page)
        if len(page) < settings.PAGE_SIZE:
            break
        offset += settings.PAGE_SIZE

    if not rows:
        return pd.DataFrame()

    wide = pd.DataFrame(rows)
    return tidy(wide, columns)


def tidy(wide: pd.DataFrame, columns: ColumnMap) -> pd.DataFrame:
    """Wide CFTC rows -> long frame keyed by (date, contract, category)."""
    base = pd.DataFrame(
        {
            "report_date": pd.to_datetime(wide[columns.date]).dt.normalize(),
            "contract_code": wide[columns.code].astype(str),
            "market_name": wide[columns.market].astype(str),
            "open_interest": pd.to_numeric(wide[columns.open_interest], errors="coerce"),
        }
    )
    base["contract_name"] = (
        wide[columns.contract_name] if columns.contract_name in wide else None
    )
    base["exchange"] = (
        wide[columns.exchange].astype("string").str.strip()
        if columns.exchange in wide
        else None
    )

    pieces = []
    for category_key, legs in columns.sides.items():
        piece = base.copy()
        piece["category"] = category_key
        piece["long"] = pd.to_numeric(wide[legs["long"]], errors="coerce")
        piece["short"] = pd.to_numeric(wide[legs["short"]], errors="coerce")
        piece["spread"] = (
            pd.to_numeric(wide[legs["spread"]], errors="coerce")
            if legs["spread"] and legs["spread"] in wide
            else pd.NA
        )
        pieces.append(piece)

    out = pd.concat(pieces, ignore_index=True)
    out["product"] = [
        pretty_name(row.market_name, row.contract_name, row.exchange)
        for row in out.itertuples()
    ]
    labels = _disambiguate(
        out[["contract_code", "product", "exchange"]].drop_duplicates("contract_code")
    ).set_index("contract_code")["product"]
    out["product"] = out["contract_code"].map(labels)
    return out.sort_values(["product", "category", "report_date"]).reset_index(drop=True)
