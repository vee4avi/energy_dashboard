"""Context for weekly stocks: changes, and the 1-year and 5-year high, low and average."""

from __future__ import annotations

import numpy as np
import pandas as pd

YEARS = 5


def seasonal(values: pd.Series) -> pd.DataFrame:
    """One series (index = week-ending dates) -> level plus context columns.

    ``avg5``/``min5``/``max5`` are the average, low and high of the same ISO week
    in the five years before; the current year is never in its own range.
    """
    values = values.dropna().sort_index()
    frame = pd.DataFrame({"value": values})
    iso = values.index.isocalendar()
    frame["year"] = iso["year"].to_numpy()
    frame["week"] = np.minimum(iso["week"].to_numpy(), 52)
    grid = frame.pivot_table(index="year", columns="week", values="value", aggfunc="last")
    past = grid.shift(1)
    stats = {
        "avg5": past.rolling(YEARS, min_periods=3).mean(),
        "min5": past.rolling(YEARS, min_periods=3).min(),
        "max5": past.rolling(YEARS, min_periods=3).max(),
    }
    for name, table in stats.items():
        long = table.stack(future_stack=True) if hasattr(table, "stack") else table
        long.index.names = ["year", "week"]
        frame[name] = long.reindex(pd.MultiIndex.from_frame(frame[["year", "week"]])).to_numpy()
    frame["wow"] = frame["value"].diff()
    frame["yoy"] = frame["value"] - frame["value"].reindex(frame.index - pd.Timedelta(days=364)).to_numpy()
    frame["vs_avg"] = frame["value"] - frame["avg5"]
    frame["vs_avg_pct"] = frame["vs_avg"] / frame["avg5"] * 100
    # Trailing 52 weeks, this one included: a plain one-year average, not seasonal.
    frame["avg1"] = frame["value"].rolling(52, min_periods=26).mean()
    frame["vs_avg1_pct"] = (frame["value"] - frame["avg1"]) / frame["avg1"] * 100
    frame["max1"] = frame["value"].rolling(52, min_periods=26).max()
    frame["min1"] = frame["value"].rolling(52, min_periods=26).min()
    return frame


def as_of_table(long_frame: pd.DataFrame, units: dict[str, str], date=None) -> pd.DataFrame:
    """One row per series for the newest week ending on or before ``date`` (default: newest).

    Rows follow the order of ``units``; a series with no reading by then is left out.
    """
    cutoff = pd.Timestamp(date) if date is not None else None
    rows = []
    for name in units:
        group = long_frame[long_frame["series"].eq(name)]
        if group.empty:
            continue
        stats = seasonal(group.set_index("period")["value"])
        if cutoff is not None:
            stats = stats[stats.index <= cutoff]
        if stats.empty:
            continue
        last = stats.iloc[-1]
        rows.append({
            "Series": name, "Unit": units.get(name, ""), "Week ending": stats.index[-1],
            "Level": last["value"], "Week change": last["wow"], "YoY change": last["yoy"],
            "1y high": last["max1"], "1y low": last["min1"],
            "1y avg": last["avg1"], "vs 1y avg %": last["vs_avg1_pct"],
            "5y high": last["max5"], "5y low": last["min5"],
            "5y avg": last["avg5"], "vs 5y avg %": last["vs_avg_pct"],
        })
    return pd.DataFrame(rows)


# Measures shown for each stock in the history table, in three blocks (a line between).
HISTORY_MEASURES = (
    (("Level", "value"), ("Week chg", "wow"), ("YoY chg", "yoy")),
    (("1y Avg", "avg1"), ("1y High", "max1"), ("1y Low", "min1")),
    (("5y Avg", "avg5"), ("5y High", "max5"), ("5y Low", "min5")),
)
HISTORY_BLOCK_STARTS = tuple(block[0][0] for block in HISTORY_MEASURES)  # "Level", "1y Avg", "5y Avg"


def history_table(values: pd.Series) -> pd.DataFrame:
    """One series, every week: dates down the side (newest first), the measures across."""
    stats = seasonal(values)
    keys = [(label, key) for block in HISTORY_MEASURES for label, key in block]
    table = pd.DataFrame({label: stats[key] for label, key in keys}, index=stats.index)
    return table.sort_index(ascending=False)


def history_wide(long_frame: pd.DataFrame, names: list[str], labels: dict[str, str] | None = None) -> pd.DataFrame:
    """Several series side by side: columns (stock, measure), weeks newest first.

    Each series' figures are worked out on its own full history before they are
    joined, so averages and highs are never cut short by another series' dates.
    """
    labels = labels or {}
    parts = {}
    for name in names:
        values = long_frame[long_frame["series"].eq(name)].set_index("period")["value"]
        if not values.empty:
            parts[labels.get(name, name)] = history_table(values)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, axis=1).sort_index(ascending=False)


def latest_table(long_frame: pd.DataFrame, units: dict[str, str]) -> pd.DataFrame:
    """One row per series for its newest week."""
    return as_of_table(long_frame, units)


def difference(current: pd.DataFrame, earlier: pd.DataFrame) -> pd.DataFrame:
    """How far each level moved between the two dates, in units and in percent."""
    now = current.set_index("Series")
    then = earlier.set_index("Series").reindex(now.index)
    out = now[["Unit"]].copy()
    out["Change"] = now["Level"] - then["Level"]
    out["Change %"] = out["Change"] / then["Level"] * 100
    return out.reset_index()


def positioning_overlay(stocks: pd.Series, positions: pd.DataFrame) -> pd.DataFrame:
    """Stocks (Friday week-endings) beside a net-position series (Tuesday dates).

    Each stock reading is matched to the latest positions on or before it, so
    nothing is looked up from the future.
    """
    stocks = stocks.dropna().rename("stocks").sort_index().reset_index().rename(columns={"index": "period", "period": "period"})
    pos = positions.sort_values("report_date")[["report_date", "net"]]
    merged = pd.merge_asof(stocks, pos, left_on="period", right_on="report_date", direction="backward",
                           tolerance=pd.Timedelta(days=6))
    return merged.dropna(subset=["net"]).set_index("period")[["stocks", "net"]]
