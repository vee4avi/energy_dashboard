"""Positioning analytics on the tidy COT frame.

Every function takes and returns a pandas frame keyed by
(report_date, contract_code, category) so the pieces compose freely.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.cftc.config import settings

KEY = ["contract_code", "category"]


def enrich(frame: pd.DataFrame, lookback: int | None = None) -> pd.DataFrame:
    """Add net positioning, week-on-week changes, z-score and COT index."""
    if frame.empty:
        return frame

    lookback = lookback or settings.DEFAULT_LOOKBACK_WEEKS
    out = frame.sort_values(KEY + ["report_date"]).copy()

    out["net"] = out["long"] - out["short"]
    out["gross"] = out["long"] + out["short"]
    oi = out["open_interest"].replace(0, np.nan)
    out["net_pct_oi"] = out["net"] / oi * 100
    out["long_pct_oi"] = out["long"] / oi * 100
    out["short_pct_oi"] = out["short"] / oi * 100
    out["long_short_ratio"] = out["long"] / out["short"].replace(0, np.nan)

    grouped = out.groupby(KEY, sort=False)
    for label, weeks in settings.CHANGE_PERIODS.items():
        out[f"net_chg_{label}"] = grouped["net"].diff(weeks)
        out[f"long_chg_{label}"] = grouped["long"].diff(weeks)
        out[f"short_chg_{label}"] = grouped["short"].diff(weeks)
        out[f"oi_chg_{label}"] = grouped["open_interest"].diff(weeks)
    out["net_pct_oi_chg_1w"] = grouped["net_pct_oi"].diff(1)

    min_obs = min(settings.MIN_LOOKBACK_OBS, lookback)

    def _zscore(series: pd.Series) -> pd.Series:
        roll = series.rolling(lookback, min_periods=min_obs)
        return (series - roll.mean()) / roll.std(ddof=0).replace(0, np.nan)

    def _cot_index(series: pd.Series) -> pd.Series:
        roll = series.rolling(lookback, min_periods=min_obs)
        low, high = roll.min(), roll.max()
        return (series - low) / (high - low).replace(0, np.nan) * 100

    out["net_z"] = grouped["net"].transform(_zscore)
    out["cot_index"] = grouped["net"].transform(_cot_index)
    out["net_pct_oi_z"] = grouped["net_pct_oi"].transform(_zscore)
    return out


def implied_options(combined: pd.DataFrame, futures: pd.DataFrame) -> pd.DataFrame:
    """Combined minus futures-only — the options leg the CFTC folds into combined.

    Both frames must be raw (pre-``enrich``) and share the same keys. Rows
    without a match on both sides are dropped, since a difference would be
    meaningless.
    """
    if combined.empty or futures.empty:
        return pd.DataFrame()

    keys = ["report_date", "contract_code", "category"]
    measures = ["long", "short", "spread", "open_interest"]
    right = futures[keys + measures].copy()
    merged = combined.merge(right, on=keys, how="inner", suffixes=("", "_fut"))
    for column in measures:
        merged[column] = merged[column] - merged[f"{column}_fut"]
    return merged.drop(columns=[f"{c}_fut" for c in measures]).reset_index(drop=True)


def report_dates(frame: pd.DataFrame) -> list[pd.Timestamp]:
    if frame.empty:
        return []
    return sorted(frame["report_date"].unique(), reverse=True)


def as_of_slice(frame: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    return frame[frame["report_date"].eq(date)].copy()


def pivot_dates(
    frame: pd.DataFrame,
    dates: list[pd.Timestamp],
    value: str = "net",
    index: tuple[str, ...] = ("product", "category"),
) -> pd.DataFrame:
    """Rows = product × category, columns = the selected report dates."""
    if frame.empty or not dates:
        return pd.DataFrame()
    subset = frame[frame["report_date"].isin(dates)]
    table = subset.pivot_table(
        index=list(index), columns="report_date", values=value, aggfunc="last"
    )
    ordered = [d for d in sorted(dates) if d in table.columns]
    return table[ordered]


def add_deltas(table: pd.DataFrame, mode: str = "vs previous") -> pd.DataFrame:
    """Append change columns to a date-pivoted table.

    ``vs previous`` compares each column to the one before it;
    ``vs first`` compares everything to the earliest selected date.
    """
    if table.empty or table.shape[1] < 2:
        return table
    out = table.copy()
    columns = list(table.columns)
    if mode == "vs first":
        base = columns[0]
        for column in columns[1:]:
            out[f"Δ {_fmt(column)} vs {_fmt(base)}"] = table[column] - table[base]
    else:
        for earlier, later in zip(columns, columns[1:]):
            out[f"Δ {_fmt(later)}"] = table[later] - table[earlier]
    return out


def changes_only(table: pd.DataFrame, mode: str = "vs previous") -> pd.DataFrame:
    full = add_deltas(table, mode)
    delta_columns = [c for c in full.columns if isinstance(c, str) and c.startswith("Δ")]
    return full[delta_columns]


def matrix(
    snapshot: pd.DataFrame, value: str = "net", categories: list[str] | None = None
) -> pd.DataFrame:
    """Product × category matrix for one report date."""
    if snapshot.empty:
        return pd.DataFrame()
    table = snapshot.pivot_table(
        index="product", columns="category", values=value, aggfunc="last"
    )
    if categories:
        table = table[[c for c in categories if c in table.columns]]
    return table


MEASURES = ("Long", "Short", "Net")


def measure_columns(pct: bool = False) -> dict[str, str]:
    """Which enriched column holds each measure, in contracts or % of open interest."""
    if pct:
        return {"Long": "long_pct_oi", "Short": "short_pct_oi", "Net": "net_pct_oi"}
    return {"Long": "long", "Short": "short", "Net": "net"}


def long_short_net(
    snapshot: pd.DataFrame,
    categories: list[str],
    pct: bool = False,
    labels: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Products down the side; Long / Short / Net under each trader category.

    One report date in, one frame out, with two-level columns
    ``(category label, measure)`` and the largest open interest first.
    """
    if snapshot.empty:
        return pd.DataFrame()
    present = [c for c in categories if c in set(snapshot["category"])]
    if not present:
        return pd.DataFrame()

    order = (
        snapshot.groupby("product")["open_interest"].max().sort_values(ascending=False).index
    )
    columns = measure_columns(pct)
    data: dict[tuple[str, str], pd.Series] = {}
    for category in present:
        subset = (
            snapshot[snapshot["category"].eq(category)]
            .drop_duplicates("product", keep="last")
            .set_index("product")
        )
        label = (labels or {}).get(category, category)
        for measure in MEASURES:
            data[(label, measure)] = subset[columns[measure]].reindex(order)

    frame = pd.DataFrame(data)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["Category", "Measure"])
    frame.index.name = "Product"
    return frame


def concentration(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Long/short split per product × category for the breakdown view."""
    if snapshot.empty:
        return pd.DataFrame()
    cols = [
        "product",
        "category",
        "long",
        "short",
        "spread",
        "net",
        "net_pct_oi",
        "long_short_ratio",
        "open_interest",
    ]
    return snapshot[[c for c in cols if c in snapshot.columns]].copy()


def summarise(snapshot: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Latest vs a chosen baseline date, one row per product × category."""
    if snapshot.empty:
        return pd.DataFrame()
    keys = ["product", "category"]
    left = snapshot.set_index(keys)
    merged = left.copy()
    if not baseline.empty:
        right = baseline.set_index(keys)[["net", "long", "short", "open_interest", "net_pct_oi"]]
        right.columns = [f"base_{c}" for c in right.columns]
        merged = left.join(right, how="left")
        merged["net_chg_base"] = merged["net"] - merged["base_net"]
        merged["long_chg_base"] = merged["long"] - merged["base_long"]
        merged["short_chg_base"] = merged["short"] - merged["base_short"]
        merged["oi_chg_base"] = merged["open_interest"] - merged["base_open_interest"]
        merged["net_pct_oi_chg_base"] = merged["net_pct_oi"] - merged["base_net_pct_oi"]
    return merged.reset_index()


def _fmt(value) -> str:
    return pd.Timestamp(value).strftime("%d %b %y")


def format_date(value) -> str:
    return _fmt(value)
