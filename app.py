"""Trading dashboard: a home page with the calendars, and a page for each section.

Run with:  streamlit run app.py
Offline preview with synthetic data:  COT_DEMO=1 streamlit run app.py

Add a section: write modules/<name>/page.py with a render() function, then add a line
to modules/registry.py. The menu and the home-page cards pick it up.
"""

from __future__ import annotations

import streamlit as st

from modules import home
from modules.registry import MODULES
from shared import access, theme

st.set_page_config(
    page_title="Trading dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject_css()
access.require_code()

PAGES = {
    module.key: st.Page(module.render, title=module.title, icon=module.icon, url_path=module.key)
    for module in MODULES
}


def _home() -> None:
    home.render(PAGES)


HOME = st.Page(_home, title="Home", icon="🏠", url_path="home", default=True)
st.navigation({"": [HOME], "Sections": list(PAGES.values())}).run()
