"""Every section of the dashboard, in one list.

Add a section by writing its ``page.py`` with a ``render()`` function and adding a line
here. The sidebar menu and the cards on the home page are both built from this list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from modules.cftc import page as cftc_page
from modules.weather import page as weather_page


@dataclass(frozen=True)
class Module:
    key: str  # url path
    title: str
    icon: str
    blurb: str
    render: Callable[[], None]
    live: bool = False


MODULES: tuple[Module, ...] = (
    Module(
        "cftc", "CFTC positioning", "⛽",
        "Who holds what in petroleum futures, week by week, with EIA stocks and the desk commentary.",
        cftc_page.render, live=True,
    ),
    Module(
        "weather", "Weather & sea state", "🌊",
        "Conditions in key coastal shipping regions that can hold up physical cargo.",
        weather_page.render,
    ),
)
