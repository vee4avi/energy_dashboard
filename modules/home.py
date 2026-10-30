"""The home page: a greeting, then the calendars stacked."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from modules.calendars import widgets

TIMEZONE = ZoneInfo("Asia/Singapore")  # the greeting follows this clock, not the server's
NAME = "trading junkie"
BEACH = "you should be at a beach."


def greeting(now: dt.datetime) -> tuple[str, str]:
    """(headline, aside) for a local time. Edit the wording here."""
    hour = now.hour
    if 5 <= hour < 12:
        headline = f"Good morning, {NAME}."
    elif 12 <= hour < 18:
        headline = f"Good afternoon, {NAME}."
    else:
        headline = f"Good evening, {NAME}."
    if now.weekday() >= 5:
        aside = f"It's the weekend — {BEACH}"
    elif 5 <= hour < 12:
        aside = f"It's too early right now — {BEACH}"
    else:
        aside = f"It's too late right now — {BEACH}"
    return headline, aside


def render(pages: dict[str, st.Page] | None = None) -> None:
    """The greeting, then the macro calendar beside the bank holidays, then expiries."""
    now = dt.datetime.now(TIMEZONE)
    headline, aside = greeting(now)
    st.markdown(
        "<div class='hello'>"
        f"<div class='hello-head'>{headline}</div>"
        f"<div class='hello-aside'>{aside} 🏖️</div>"
        f"<div class='hello-time'>{now:%A %d %B %Y · %H:%M} Singapore</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    macro, holidays = st.columns([5, 6], gap="large")
    with macro:
        widgets.macro_box()
    with holidays:
        widgets.holidays_box(now.date())
    expiries, _ = st.columns([5, 6], gap="large")
    with expiries:
        widgets.expiries_box(now.date())
