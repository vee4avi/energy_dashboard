"""Petroleum positioning dashboard: CFTC Commitments of Traders plus EIA storage.

Run with:  streamlit run app.py
Offline preview with synthetic data:  COT_DEMO=1 streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

from modules.cftc import page
from shared import access, theme

st.set_page_config(
    page_title="Petroleum positioning",
    page_icon="⛽",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject_css()
access.require_code()
page.render()
