"""Entry script for AppTest: the CFTC page on its own, without the router."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from modules.cftc import page  # noqa: E402
from shared import theme  # noqa: E402

st.set_page_config(layout="wide")
theme.inject_css()
page.render()
