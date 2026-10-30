"""The home page: a greeting, a card for each section, then the calendars stacked."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import streamlit as st

from modules.calendars import widgets
from modules.cftc import services as cftc_services
from modules.registry import MODULES, Module

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
    elif 5 <= hour < 8:
        aside = f"It's too early right now — {BEACH}"
    elif hour >= 21 or hour < 5:
        aside = f"It's too late right now — {BEACH}"
    else:
        aside = ""
    return headline, aside


def _status(module: Module) -> str:
    if module.key == "cftc":
        friday, covers = cftc_services.next_release()
        return f"Next report **{friday:%a %d %b}**, covering positions at {covers:%d %b}."
    return ""


def _cards(pages: dict[str, st.Page]) -> None:
    columns = st.columns(len(MODULES) + 1, gap="medium")  # one spare column keeps cards compact
    for column, module in zip(columns, MODULES):
        with column, st.container(border=True, height=190):
            badge = ":green[Live]" if module.live else ":gray[Coming soon]"
            st.markdown(f"**{module.icon} {module.title}**  {badge}")
            st.caption(module.blurb)
            status = _status(module)
            if status:
                st.caption(status)
            if module.live:
                st.page_link(pages[module.key], label="Open", icon="➡️")


def render(pages: dict[str, st.Page]) -> None:
    """``pages`` maps each section key to its navigation page, for the links."""
    now = dt.datetime.now(TIMEZONE)
    headline, aside = greeting(now)
    st.markdown(f"<div class='sec-title' style='font-size:26px'>{headline}</div>", unsafe_allow_html=True)
    st.caption(f"{now:%A %d %B %Y, %H:%M} Singapore" + (f"  ·  {aside}" if aside else ""))

    _cards(pages)
    widgets.macro_box()
    widgets.holidays_box(now.date())
    widgets.expiries_box(now.date())
