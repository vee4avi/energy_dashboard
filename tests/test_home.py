"""Tests for the home page: greeting, calendars and expiries (offline).

Run with:  python tests/test_home.py
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["COT_DEMO"] = "1"

from modules import home  # noqa: E402
from modules.calendars import data_sources, widgets  # noqa: E402

SGT = home.TIMEZONE


def at(day: str, hour: int) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day} {hour:02d}:30").replace(tzinfo=SGT)


def test_greeting() -> None:
    day = "2026-10-28"  # a Wednesday
    assert home.greeting(at(day, 2)) == ("Good evening, trading junkie.", "It's past midnight — why on earth are you awake? 🦉")
    assert home.greeting(at(day, 6)) == ("Good morning, trading junkie.", "It's too early right now — you should be in bed. 🛏️")
    assert home.greeting(at(day, 11))[1].endswith("in bed. 🛏️")
    assert home.greeting(at(day, 12)) == ("Good afternoon, trading junkie.", "It's midday — you should be at a beach. 🏖️")
    assert home.greeting(at(day, 16)) == ("Good afternoon, trading junkie.", "It's late — you should be getting a drink. 🍹")
    assert home.greeting(at(day, 18)) == ("Good evening, trading junkie.", "It's late — go grab a bottle of wine. 🍷")
    assert home.greeting(at(day, 23))[1].endswith("bottle of wine. 🍷")
    for hour in (2, 9, 14, 20):  # Saturday, any time
        assert home.greeting(at("2026-10-31", hour))[1] == "It's the weekend — you should be at a beach. 🏖️"
    print("greeting: ok")


def test_when() -> None:
    today = dt.date(2026, 10, 30)
    days = lambda n: widgets.when(today + dt.timedelta(days=n), today)  # noqa: E731
    assert [days(0), days(1), days(5), days(14)] == ["today", "tomorrow", "in 5 days", "in 14 days"]
    assert [days(15), days(21), days(30)] == ["in 2 weeks", "in 3 weeks", "in 4 weeks"]
    assert [days(31), days(45), days(61), days(200)] == ["in 1 month", "in 1 month", "in 2 months", "in 7 months"]
    print("when: ok")


def test_holidays() -> None:
    frame = data_sources.holidays_between(dt.date(2026, 12, 1), dt.date(2027, 2, 28), list(data_sources.COUNTRIES))
    assert set(frame["Country"]) == {"US", "UK", "Singapore", "China"}
    days = {(r.Country, r.Date) for r in frame.itertuples()}
    assert ("US", dt.date(2026, 12, 25)) in days and ("UK", dt.date(2026, 12, 28)) in days, "UK Boxing Day substitute"
    assert ("Singapore", dt.date(2026, 12, 25)) in days
    assert any(c == "China" and d.month == 2 for c, d in days), "Chinese New Year"
    assert frame["Date"].is_monotonic_increasing
    china = frame[frame["Country"].eq("China")]["Holiday"]
    assert all(name.isascii() for name in china), "names in English"
    print("holidays: ok")


def test_expiries_match_ice_and_its_rule() -> None:
    frame = data_sources.expiries_between(dt.date(2026, 11, 1), dt.date(2027, 1, 31), data_sources.expiry_products())
    rows = {(r.Product, r.Contract): r.Date for r in frame.itertuples()}
    # Straight from ICE's expiry pages.
    assert rows[("Brent futures", "Jan27")] == dt.date(2026, 11, 30)
    assert rows[("Brent futures", "Feb27")] == dt.date(2026, 12, 30), "the day before New Year's Eve"
    assert rows[("Brent options", "Jan27")] == dt.date(2026, 11, 25)
    assert rows[("Brent options", "Feb27")] == dt.date(2026, 12, 23)
    assert frame["Date"].is_monotonic_increasing

    # ICE's rule: options stop three business days before the futures, a day earlier if
    # that lands on US Thanksgiving. Checked across every month held, to catch typos.
    import holidays

    uk = holidays.country_holidays("GB", subdiv="ENG", years=range(2026, 2034))
    business = lambda d: d.weekday() < 5 and d not in uk  # noqa: E731
    contracts = data_sources._expiry_data()["contracts"]
    for month, option_day in contracts["Brent options"]["dates"].items():
        option_day = dt.date.fromisoformat(option_day)
        future_day = dt.date.fromisoformat(contracts["Brent futures"]["dates"][month])
        gap = sum(business(option_day + dt.timedelta(k)) for k in range(1, (future_day - option_day).days + 1))
        thanksgiving = option_day + dt.timedelta(days=1)
        assert gap == 3 or (gap == 4 and thanksgiving.month == 11 and thanksgiving.weekday() == 3), (month, gap)
    assert data_sources.last_listed("Brent options") >= dt.date(2032, 10, 1)
    print("expiries: ok")


def test_greeting_panel() -> None:
    from modules import greeting_panel

    now = at("2026-10-28", 15)
    markup = greeting_panel.panel_html("Good afternoon, trading junkie.", "It's midday <b>", now)
    assert "Good afternoon, trading junkie." in markup and "It&#x27;s midday &lt;b&gt;" in markup, "escaped"
    for zone in ("Asia/Singapore", "Europe/London", "America/New_York"):
        assert f'data-tz="{zone}"' in markup, zone
    assert 'data-market="NASDAQ"' in markup and '"open": "09:30"' in markup
    assert '"2026-11-26"' in markup, "NYSE holidays (Thanksgiving) feed the open/closed badge"
    assert "setInterval(tick, 1000)" in markup
    print("greeting panel: ok")


def test_table_html() -> None:
    import pandas as pd

    frame = pd.DataFrame({"Date": ["Fri 30 Oct"], "Holiday": ["<b>x</b>"], "When": ["in 3 days"]})
    markup = widgets.table_html(frame, 200)
    assert "max-height:200px" in markup and "&lt;b&gt;" in markup, "fixed height; text escaped"
    assert '<td class="soon">in 3 days</td>' in markup
    assert '<td class="soon">' not in widgets.table_html(frame.assign(When=["in 2 weeks"]), 200)
    print("table html: ok")


def test_tradingview_html() -> None:
    markup = widgets.tradingview_html(["High"], ["United States", "China"], 300)
    assert 'src="https://s3.tradingview.com/external-embedding/embed-widget-events.js"' in markup
    assert '"importanceFilter": "1"' in markup and '"countryFilter": "us,cn"' in markup
    assert '"height": "300"' in markup and "TradingView" in markup, "fixed height; attribution kept"
    assert "tv-market-summary" in widgets.MARKET_SUMMARY_EMBED
    print("tradingview: ok")


def test_home_page_renders() -> None:
    from streamlit.testing.v1 import AppTest

    os.chdir(ROOT)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not app.exception, [e.value for e in app.exception]
    text = "\n".join(m.value for m in app.markdown)
    for title in ("Market summary", "Macro calendar", "Bank holidays", "Contract expiries"):
        assert title in text, title
    assert not app.multiselect, "no filters: everything is shown"
    tables = [m.value for m in app.markdown if 'class="cal"' in m.value]
    assert len(tables) == 2, "bank holidays and expiries"
    assert "<th>Date</th><th>Country</th><th>Holiday</th><th>When</th>" in tables[0]
    for country in ("US", "UK", "Singapore", "China"):
        assert f"<td>{country}</td>" in tables[0], country
    assert "Brent futures" in tables[1] and "Brent options" in tables[1]
    assert all("\n" not in t for t in tables), "one line, so Markdown leaves it alone"
    assert "Live" not in text, "no section cards on the home page"
    print("home page: ok")


if __name__ == "__main__":
    test_greeting()
    test_when()
    test_holidays()
    test_expiries_match_ice_and_its_rule()
    test_greeting_panel()
    test_table_html()
    test_tradingview_html()
    test_home_page_renders()
    print("\nall home tests passed")
