"""The calendar boxes on the home page: each a fixed height, scrolling inside."""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modules.calendars import data_sources
from shared import theme

BOX_HEIGHT = 520  # px, every calendar box (scrolls inside)
TV_SCRIPT = "https://s3.tradingview.com/external-embedding/embed-widget-events.js"
TV_IMPORTANCE = {"High": "1", "Medium": "0", "Low": "-1"}
TV_COUNTRIES = {
    "United States": "us", "Euro area": "eu", "United Kingdom": "gb", "China": "cn",
    "Japan": "jp", "Singapore": "sg", "India": "in", "Saudi Arabia": "sa",
}


def _embed(markup: str, height: int) -> None:
    """Our own HTML in an iframe (st.iframe in newer Streamlit, components.html before)."""
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:
        components.html(markup, height=height, scrolling=False)


def tradingview_html(importance: list[str], countries: list[str], height: int) -> str:
    config = {
        "colorTheme": "light",
        "isTransparent": False,
        "width": "100%",
        "height": str(height),
        "locale": "en",
        "importanceFilter": ",".join(TV_IMPORTANCE[i] for i in importance),
        "countryFilter": ",".join(TV_COUNTRIES[c] for c in countries),
    }
    payload = json.dumps(config).replace("</", "<\\/")  # nothing may close the script tag early
    return (
        '<div class="tradingview-widget-container"><div class="tradingview-widget-container__widget"></div>'
        '<div class="tradingview-widget-copyright" style="font:11px sans-serif;padding-top:2px">'
        '<a href="https://www.tradingview.com/economic-calendar/" rel="noopener nofollow" target="_blank">'
        "Economic calendar</a> by TradingView</div>"
        f'<script type="text/javascript" src="{TV_SCRIPT}" async>{payload}</script></div>'
    )


def when(date: dt.date, today: dt.date) -> str:
    """How far off a date is: days up to two weeks, then weeks, then months past 30 days."""
    gap = (date - today).days
    if gap == 0:
        return "today"
    if gap == 1:
        return "tomorrow"
    if gap <= 14:
        return f"in {gap} days"
    if gap <= 30:
        weeks = round(gap / 7)
        return f"in {weeks} week{'s' if weeks != 1 else ''}"
    months = max(1, round(gap / 30.44))
    return f"in {months} month{'s' if months != 1 else ''}"


def _box(key: str, title: str):
    """A bordered box with a coloured title strip; the CSS lives in theme.PAGE_CSS."""
    box = st.container(key=f"calbox_{key}")
    box.markdown(f"<div class='cal-title'>{title}</div>", unsafe_allow_html=True)
    return box


def macro_box() -> None:
    with _box("macro", "Macro calendar"):
        _embed(tradingview_html(list(TV_IMPORTANCE), list(TV_COUNTRIES), BOX_HEIGHT), BOX_HEIGHT + 24)


def _table(frame: pd.DataFrame) -> None:
    st.dataframe(frame, hide_index=True, height=BOX_HEIGHT, **theme.wide())


def holidays_box(today: dt.date) -> None:
    with _box("holidays", "Bank holidays"):
        frame = data_sources.holidays_between(
            today, today + dt.timedelta(days=365), list(data_sources.COUNTRIES)
        )
        if frame.empty:
            st.caption("No bank holidays in the next 12 months.")
            return
        _table(pd.DataFrame({
            "Date": [f"{d:%a %d %b %Y}" for d in frame["Date"]],
            "Country": frame["Country"],
            "Holiday": frame["Holiday"],
            "When": [when(d, today) for d in frame["Date"]],
        }))
        st.caption("US, UK (England), Singapore and China. Exchange schedules can differ.")


def expiries_box(today: dt.date) -> None:
    with _box("expiries", "Contract expiries"):
        frame = data_sources.expiries_between(
            today, today + dt.timedelta(days=3 * 365), data_sources.expiry_products()
        )
        if frame.empty:
            st.caption("No expiries held; add months to the expiries file.")
            return
        _table(pd.DataFrame({
            "Expiry": [f"{d:%a %d %b %Y}" for d in frame["Date"]],
            "Product": frame["Product"],
            "Contract": frame["Contract"],
            "When": [when(d, today) for d in frame["Date"]],
        }))
        st.caption("Last trading days as published by ICE (Brent futures and Brent options).")
