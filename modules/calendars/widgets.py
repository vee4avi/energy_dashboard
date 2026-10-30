"""The calendar boxes on the home page: each a fixed height, scrolling inside."""

from __future__ import annotations

import datetime as dt
import json

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modules.calendars import data_sources
from shared import theme

BOX_HEIGHT = 330  # px, every calendar box
TV_SCRIPT = "https://s3.tradingview.com/external-embedding/embed-widget-events.js"
TV_IMPORTANCE = {"High": "1", "Medium": "0", "Low": "-1"}
TV_COUNTRIES = {
    "United States": "us", "Euro area": "eu", "United Kingdom": "gb", "China": "cn",
    "Japan": "jp", "Singapore": "sg", "India": "in", "Saudi Arabia": "sa",
}
TV_DEFAULT_COUNTRIES = ("United States", "Euro area", "United Kingdom", "China", "Singapore")


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


def macro_box() -> None:
    with st.container(border=True):
        head, one, two = st.columns([2, 2, 4])
        head.markdown("**Macro calendar**")
        importance = one.multiselect(
            "Importance", list(TV_IMPORTANCE), default=["High", "Medium"], key="home_tv_importance",
            label_visibility="collapsed", placeholder="Importance",
        )
        countries = two.multiselect(
            "Countries", list(TV_COUNTRIES), default=list(TV_DEFAULT_COUNTRIES), key="home_tv_countries",
            label_visibility="collapsed", placeholder="Countries",
        )
        if not importance or not countries:
            st.caption("Pick at least one importance level and one country.")
            return
        _embed(tradingview_html(importance, countries, BOX_HEIGHT), BOX_HEIGHT + 24)


def _table(frame: pd.DataFrame) -> None:
    st.dataframe(frame, hide_index=True, height=BOX_HEIGHT, **theme.wide())


def _days(date: dt.date, today: dt.date) -> str:
    gap = (date - today).days
    return "today" if gap == 0 else ("tomorrow" if gap == 1 else f"in {gap}d")


def holidays_box(today: dt.date) -> None:
    with st.container(border=True):
        head, pick = st.columns([2, 6])
        head.markdown("**Holidays**")
        countries = pick.multiselect(
            "Countries", list(data_sources.COUNTRIES), default=list(data_sources.COUNTRIES),
            key="home_holiday_countries", label_visibility="collapsed", placeholder="Countries",
        )
        if not countries:
            st.caption("Pick at least one country.")
            return
        frame = data_sources.holidays_between(today, today + dt.timedelta(days=365), countries)
        if frame.empty:
            st.caption("No public holidays in the next 12 months.")
            return
        _table(pd.DataFrame({
            "Date": [f"{d:%a %d %b %Y}" for d in frame["Date"]],
            "When": [_days(d, today) for d in frame["Date"]],
            "Country": frame["Country"],
            "Holiday": frame["Holiday"],
        }))
        st.caption("Public holidays (UK = England). Exchange schedules can differ; check the exchange notice.")


def expiries_box(today: dt.date) -> None:
    with st.container(border=True):
        head, pick = st.columns([2, 6])
        head.markdown("**Contract expiries**")
        products = data_sources.expiry_products()
        chosen = pick.multiselect(
            "Contracts", products, default=products, key="home_expiry_products",
            label_visibility="collapsed", placeholder="Contracts",
        )
        if not chosen:
            st.caption("Pick at least one contract.")
            return
        frame = data_sources.expiries_between(today, today + dt.timedelta(days=3 * 365), chosen)
        if frame.empty:
            st.caption("No expiries held for these contracts; add months to the expiries file.")
            return
        _table(pd.DataFrame({
            "Expiry": [f"{d:%a %d %b %Y}" for d in frame["Date"]],
            "When": [_days(d, today) for d in frame["Date"]],
            "Product": frame["Product"],
            "Contract": frame["Contract"],
        }))
        st.caption("Last trading days as published by ICE (Brent futures and Brent options).")
