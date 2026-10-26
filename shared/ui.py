"""Small building blocks shared by every module's page."""

from __future__ import annotations

import streamlit as st


def coming_soon(title: str, icon: str, summary: str, planned: list[str], sources: list[str]) -> None:
    """A placeholder page for a module that has not been built yet."""
    st.markdown(f"## {icon} {title}")
    st.info("This module is not built yet.", icon="🚧")
    st.markdown(summary)
    columns = st.columns(2, gap="large")
    with columns[0]:
        st.markdown("**Planned**")
        st.markdown("\n".join(f"- {item}" for item in planned))
    with columns[1]:
        st.markdown("**Data sources to settle**")
        st.markdown("\n".join(f"- {item}" for item in sources))
