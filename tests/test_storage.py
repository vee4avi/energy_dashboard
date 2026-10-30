"""Tests for the EIA storage tab (offline).

Run with:  python tests/test_storage.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["COT_DEMO"] = "1"

from modules.cftc.analytics import storage  # noqa: E402
from modules.cftc.sources import demo, eia  # noqa: E402

PAYLOAD = {"response": {"total": 3, "data": [
    {"period": "2026-10-16", "series": "WCESTUS1", "value": "420123", "units": "MBBL"},
    {"period": "2026-10-09", "series": "WCESTUS1", "value": "418000", "units": "MBBL"},
    {"period": "2026-10-16", "series": "NW2_EPG0_SWO_R48_BCF", "value": "3800"},
    {"period": "2026-10-16", "series": "OTHER", "value": "1"},
    {"period": "2026-10-16", "series": "WGTSTUS1", "value": None},
]}}


def test_parse_scales_and_filters() -> None:
    frame = eia.parse(PAYLOAD)
    crude = frame[frame["series"].eq("Crude (commercial)")].sort_values("period")
    assert list(crude["value"]) == [418.0, 420.123], "thousand barrels become million barrels"
    assert frame[frame["series"].eq("Natural gas")]["value"].iloc[0] == 3800.0
    assert set(frame["series"]) == {"Crude (commercial)", "Natural gas"}, "unknown and empty rows dropped"
    print("parse: ok")


def test_errors_never_leak_the_key() -> None:
    import requests

    class Boom:
        status_code = 403

    original = requests.get
    try:
        requests.get = lambda *a, **k: Boom()
        try:
            eia.fetch("SECRET-KEY-123")
        except eia.EiaError as error:
            assert "SECRET-KEY-123" not in str(error) and "EIA_API_KEY" in str(error)
        else:
            raise AssertionError("expected EiaError")

        def refuse(*a, **k):
            raise requests.ConnectionError("https://api.eia.gov/?api_key=SECRET-KEY-123")

        requests.get = refuse
        try:
            eia.fetch("SECRET-KEY-123")
        except eia.EiaError as error:
            assert "SECRET-KEY-123" not in str(error)
    finally:
        requests.get = original
    print("key hygiene: ok")


def test_seasonal_stats() -> None:
    weeks = pd.date_range("2020-01-03", periods=52 * 7, freq="7D")
    values = pd.Series(range(len(weeks)), index=weeks, dtype=float)
    stats = storage.seasonal(values)
    last = stats.iloc[-1]
    assert last["wow"] == 1.0 and last["yoy"] == 52.0
    previous_years = [last["value"] - 52 * k for k in range(1, 6)]
    assert abs(last["avg5"] - sum(previous_years) / 5) < 1.5  # same ISO week, +-1 week of drift
    assert last["min5"] < last["avg5"] < last["max5"]
    assert stats["avg5"].iloc[:60].isna().all(), "no range before there are years to compare with"
    print("seasonal: ok")


def test_latest_table_and_overlay() -> None:
    data = demo.storage()
    table = storage.latest_table(data, {s.key: s.unit for s in eia.SERIES})
    assert list(table["Series"]) == [s.key for s in eia.SERIES]
    assert table["Level"].notna().all() and table["vs 5y avg %"].notna().all()

    assert list(table["Series"]) == ["Crude (commercial)", "SPR", "Cushing crude", "Gasoline",
                                     "Distillate", "Jet fuel", "Natural gas"]
    units = {s.key: s.unit for s in eia.SERIES}
    older = storage.as_of_table(data, units, table["Week ending"].max() - pd.Timedelta(days=7))
    assert (older["Week ending"] == table["Week ending"].max() - pd.Timedelta(days=7)).all()
    change = storage.difference(table, older)
    assert abs(change.loc[0, "Change"] - (table.loc[0, "Level"] - older.loc[0, "Level"])) < 1e-9
    assert abs(change.loc[0, "Change"] - table.loc[0, "Week change"]) < 1e-9, "one week apart = the weekly change"
    assert abs(change.loc[0, "Change %"] - change.loc[0, "Change"] / older.loc[0, "Level"] * 100) < 1e-9
    row = table.iloc[0]
    assert row["1y low"] <= row["1y avg"] <= row["1y high"] and row["5y low"] <= row["5y avg"] <= row["5y high"]
    assert storage.as_of_table(data, units, "2000-01-01").empty

    stocks = data[data["series"].eq("Gasoline")].set_index("period")["value"]
    positions = pd.DataFrame({
        "report_date": pd.date_range("2025-01-07", periods=60, freq="7D"), "net": range(60),
    })
    merged = storage.positioning_overlay(stocks, positions)
    assert not merged.empty and merged["net"].notna().all()
    first = merged.index[0]
    paired = positions[positions["report_date"].le(first)]["report_date"].max()
    assert (first - paired).days <= 6, "positions come from on or before the stock date"
    print("table and overlay: ok")


def test_compact_table_and_news_markup() -> None:
    from shared import notes, tables

    table = storage.latest_table(demo.storage(), {s.key: s.unit for s in eia.SERIES})
    markup = tables.stocks_html(table)
    assert "\n" not in markup and markup.count("<tr>") == 1 + len(table)
    assert "Crude (commercial)" in markup and "(Bcf)" in markup
    shaded = [c for c in tables.STOCK_COLUMNS if c[0] not in tables.STOCK_PLAIN_COLUMNS]
    assert markup.count("background:#") == len(table) * len(shaded), "only moves and % gaps are shaded"
    assert {c[0] for c in shaded} == {"Week change", "YoY change", "vs 1y avg %", "vs 5y avg %"}
    assert "<th class=\"sub gstart\">1y avg</th><th class=\"sub\">chg %</th>" in markup and "<br>" not in markup and "(Δ " not in markup, "average and its % gap share a cell"
    assert tables.delta_pct(-8.24) == "-8.2%" and tables.delta_pct(0.01) == "+0.0%"
    limits = tables.stock_limits(table)
    assert limits[("Level", "mb")] == table[table["Unit"].eq("mb")]["Level"].abs().max()
    assert limits[("Level", "bcf")] != limits[("Level", "mb")], "barrels and Bcf have their own scales"
    assert limits[("Level", "bcf")] > 1000 and limits[("Level", "mb")] < 1000, "oil and gas have their own scales"
    moves = tables.stocks_html(storage.difference(table, table), columns=tables.STOCK_CHANGE_COLUMNS)
    assert "\n" not in moves and "Week change" not in moves and ">+0.0</td>" in moves and ">+0.0%</td>" in moves
    assert moves.count("background:#") == len(table), "only the Δ% column is shaded"
    assert moves.count("<th class=\"sub") == 2 and ">Δ%</th>" in moves, "change table: Change and Δ%"
    news = notes.body_html("## Headlines\n- Oil up [Reuters](https://example.com/a?x=1&y=2) on **supply**\n- $5 move")
    assert '<a href="https://example.com/a?x=1&amp;y=2"' in news and "<strong>supply</strong>" in news
    assert "<p><strong>Headlines</strong></p>" in news and "&#36;5" in news
    print("compact table and news: ok")


def test_history_table() -> None:
    from shared import tables

    data = demo.storage()
    series = data[data["series"].eq("Gasoline")].set_index("period")["value"]
    one = storage.history_table(series)
    assert one.index.is_monotonic_decreasing, "newest week first"
    assert list(one.columns) == [
        "Level", "Week chg", "YoY chg", "1y Avg", "1y High", "1y Low", "5y Avg", "5y High", "5y Low"]
    newest, previous = one.index[0], one.index[1]
    assert abs(one.loc[newest, "Week chg"] - (one.loc[newest, "Level"] - one.loc[previous, "Level"])) < 1e-9
    snapshot = storage.as_of_table(data, {"Gasoline": "mb"})
    assert abs(snapshot.loc[0, "5y avg"] - one.loc[newest, "5y Avg"]) < 1e-9, "same numbers as Snapshot"
    assert one.loc[newest, "1y Low"] <= one.loc[newest, "1y Avg"] <= one.loc[newest, "1y High"]

    wide = storage.history_wide(data, ["Crude (commercial)", "SPR"], {"SPR": "SPR stocks"})
    assert list(dict.fromkeys(wide.columns.get_level_values(0))) == ["Crude (commercial)", "SPR stocks"]
    assert wide.shape[1] == 18 and wide.index.is_monotonic_decreasing
    assert storage.history_wide(data, []).empty

    markup = tables.stocks_history_html(wide.head(4))
    assert "\n" not in markup and markup.count("<tr>") == 2 + 4
    assert markup.count('class="hd grp gs2"') == 2, "one header per stock"
    assert markup.count("gs2") >= 2 + 2 + 2 * 4, "a heavy line before each stock"
    assert 'class="hd sub gs">1y Avg' in markup and 'class="hd sub gs">5y Avg' in markup
    assert 'class="up' in markup or 'class="down' in markup
    assert tables._stock_history_cell(-1.26, "Week chg") == ("-1.3", "down")
    assert tables._stock_history_cell(215.04, "Level") == ("215.0", "")
    assert tables._stock_history_cell(float("nan"), "1y Avg") == ("", "blank")
    print("history table: ok")


def test_tab_runs() -> None:
    from streamlit.testing.v1 import AppTest

    os.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    text = "\n".join(m.value for m in at.markdown)
    assert "US stocks (EIA)" in text and "sec-rule" in text and text.count("Week ending") >= 2
    at.tabs  # the Storage tab: every stock at once, then one, then none
    every = list(at.multiselect(key="storage_stocks").options)
    at.multiselect(key="storage_stocks").set_value(every).run()
    assert not at.exception, [e.value for e in at.exception]
    at.selectbox(key="storage_window").set_value("1 year").run()
    assert not at.exception, [e.value for e in at.exception]
    for series in at.selectbox(key="storage_series").options:
        at.selectbox(key="storage_series").set_value(series).run()
        assert not at.exception, (series, [e.value for e in at.exception])
    at.radio(key="storage_view").set_value("With positioning").run()
    assert not at.exception, [e.value for e in at.exception]
    for product in at.selectbox(key="storage_product").options:
        at.selectbox(key="storage_product").set_value(product).run()
        assert not at.exception, (product, [e.value for e in at.exception])
    print("storage tab runs: ok")


def test_tab_asks_for_a_key() -> None:
    from streamlit.testing.v1 import AppTest

    import modules.cftc.services as services

    os.chdir(ROOT)
    os.environ["COT_DEMO"] = "1"
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.run()
    # With no key and not in demo mode the tab should explain, not crash.
    services.DEMO_MODE = False
    try:
        os.environ.pop("EIA_API_KEY", None)
        assert not services.eia_available()
        try:
            services.load_storage()
        except eia.EiaError as error:
            assert "EIA_API_KEY" in str(error)
        else:
            raise AssertionError("expected EiaError")
    finally:
        services.DEMO_MODE = True
    print("missing key: ok")


if __name__ == "__main__":
    test_parse_scales_and_filters()
    test_errors_never_leak_the_key()
    test_seasonal_stats()
    test_latest_table_and_overlay()
    test_compact_table_and_news_markup()
    test_history_table()
    test_tab_runs()
    test_tab_asks_for_a_key()
    print("\nall storage tests passed")
