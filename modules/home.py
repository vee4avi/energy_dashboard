"""The home page: a greeting, then the calendars stacked."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from modules import greeting_panel
from modules.calendars import widgets

TIMEZONE = ZoneInfo("Asia/Singapore")  # the greeting follows this clock, not the server's
NAME = "trading junkie"
BEACH = "you should be at a beach."


def greeting(now: dt.datetime) -> tuple[str, str]:
    """(headline, aside) for a local time. Edit the wording here."""
    hour = now.hour
    if hour < 6:
        headline = f"Good evening, {NAME}."
    elif hour < 12:
        headline = f"Good morning, {NAME}."
    elif hour < 18:
        headline = f"Good afternoon, {NAME}."
    else:
        headline = f"Good evening, {NAME}."

    if now.weekday() >= 5:
        aside = f"It's the weekend — {BEACH} 🏖️"
    elif hour < 6:
        aside = "It's past midnight — why on earth are you awake? 🦉"
    elif hour < 12:
        aside = "It's too early right now — you should be in bed. 🛏️"
    elif hour < 16:
        aside = f"It's midday — {BEACH} 🏖️"
    elif hour < 18:
        aside = "It's late — you should be getting a drink. 🍹"
    else:
        aside = "It's late — go grab a bottle of wine. 🍷"
    return headline, aside


def render(pages: dict[str, st.Page] | None = None) -> None:
    """The greeting, TradingView's market summary, then the three calendars side by side."""
    now = dt.datetime.now(TIMEZONE)
    headline, aside = greeting(now)
    widgets._embed(greeting_panel.panel_html(headline, aside, now), greeting_panel.PANEL_HEIGHT)
    widgets.market_summary_box()
    macro, holidays, expiries = st.columns(3, gap="medium")
    with macro:
        widgets.macro_box()
    with holidays:
        widgets.holidays_box(now.date())
    with expiries:
        widgets.expiries_box(now.date())
