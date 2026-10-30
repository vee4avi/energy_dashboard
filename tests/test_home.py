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
    # Wed 28 Oct 2026, a weekday
    assert home.greeting(at("2026-10-28", 6)) == ("Good morning, trading junkie.", "It's too early right now — you should be at a beach.")
    assert home.greeting(at("2026-10-28", 10)) == ("Good morning, trading junkie.", "")
    assert home.greeting(at("2026-10-28", 15)) == ("Good afternoon, trading junkie.", "")
    assert home.greeting(at("2026-10-28", 19)) == ("Good evening, trading junkie.", "")
    assert home.greeting(at("2026-10-28", 22))[1] == "It's too late right now — you should be at a beach."
    assert home.greeting(at("2026-10-28", 2)) == ("Good evening, trading junkie.", "It's too late right now — you should be at a beach.")
    assert home.greeting(at("2026-10-31", 11))[1] == "It's the weekend — you should be at a beach."  # Saturday
    print("greeting: ok")


def test_holidays() -> None:
    frame = data_sources.holidays_between(dt.date(2026, 12, 1), dt.date(2027, 2, 28), list(data_sources.COUNTRIES))
    assert set(frame["Country"]) == {"US", "UK", "Singapore", "China"}
    days = {(r.Country, r.Date) for r in frame.itertuples()}
    assert ("US", dt.date(2026, 12, 25)) in days and ("UK", dt.date(2026, 12, 28)) in days, "UK Boxing Day substitute"
    assert ("Singapore", dt.date(2026, 12, 25)) in days
    assert any(c == "China" and d.month == 2 for c, d in days), "Chinese New Year"
    assert frame["Date"].is_monotonic_increasing
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


def test_tradingview_html() -> None:
    markup = widgets.tradingview_html(["High"], ["United States", "China"], 300)
    assert 'src="https://s3.tradingview.com/external-embedding/embed-widget-events.js"' in markup
    assert '"importanceFilter": "1"' in markup and '"countryFilter": "us,cn"' in markup
    assert '"height": "300"' in markup and "TradingView" in markup, "fixed height; attribution kept"
    print("tradingview: ok")


def test_boxes_render_and_filter() -> None:
    from streamlit.testing.v1 import AppTest

    os.chdir(ROOT)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    assert not app.exception, [e.value for e in app.exception]
    assert len(app.dataframe) == 2, "holidays and expiries"
    app.multiselect(key="home_holiday_countries").set_value(["China"]).run()
    app.multiselect(key="home_expiry_products").set_value(["Brent options"]).run()
    assert not app.exception, [e.value for e in app.exception]
    app.multiselect(key="home_expiry_products").set_value([]).run()
    app.multiselect(key="home_tv_countries").set_value([]).run()
    assert not app.exception
    captions = "\n".join(c.value for c in app.caption)
    assert "Pick at least one contract." in captions and "Pick at least one importance" in captions
    print("home boxes: ok")


if __name__ == "__main__":
    test_greeting()
    test_holidays()
    test_expiries_match_ice_and_its_rule()
    test_tradingview_html()
    test_boxes_render_and_filter()
    print("\nall home tests passed")
