"""Keep widget state valid when the option lists change underneath it.

Streamlit raises if a widget's stored value is no longer one of its options —
which happens the moment you shorten the history window with an old report
date selected, or hide thin contracts while one is picked. These helpers run
just before each widget is created.
"""

from __future__ import annotations

from typing import Sequence

import streamlit as st


def prune_multiselect(key: str, options: Sequence) -> None:
    if key not in st.session_state:
        return
    allowed = list(options)
    kept = [value for value in st.session_state[key] if value in allowed]
    if len(kept) != len(st.session_state[key]):
        st.session_state[key] = kept


def ensure_option(key: str, options: Sequence) -> None:
    if key in st.session_state and st.session_state[key] not in list(options):
        del st.session_state[key]


def ensure_range(key: str, low, high) -> None:
    if key not in st.session_state:
        return
    value = st.session_state[key]
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        del st.session_state[key]
        return
    start, end = value
    if start < low or end > high or start > end:
        del st.session_state[key]


# --------------------------------------------------------------------------
# Keeping a page's widgets when you move to another page
# --------------------------------------------------------------------------
# Streamlit forgets the value of any widget that is not drawn in a run, so a
# trip to another page would reset every filter. A page calls save() once it has
# drawn its widgets and remember() when it starts: values are copied to plain
# keys, which Streamlit does keep, and put back if the widget has lost them.
_COPY = "_kept__"
_NOT_WIDGET_STATE = {"app_code"}  # typed secrets are never copied
_BUTTONS = ("analysis_run", "analysis_download", "storage_download")  # buttons cannot be given a value


def save() -> None:
    for key, value in list(st.session_state.items()):
        if key.startswith("_") or key in _NOT_WIDGET_STATE or key in _BUTTONS:
            continue
        try:
            st.session_state[_COPY + key] = value
        except Exception:  # noqa: BLE001 - never let bookkeeping break a page
            pass


def remember() -> None:
    for key in [k for k in st.session_state if k.startswith(_COPY)]:
        original = key[len(_COPY):]
        if original not in st.session_state:
            st.session_state[original] = st.session_state[key]
