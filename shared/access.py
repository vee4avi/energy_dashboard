"""An optional access code for the whole app.

If ``APP_PASSWORD`` is set (environment or secrets), nothing renders until the
visitor types it. Leave it unset for local use. Community Cloud apps are public
by default, so set it there, or restrict viewers in the app's sharing settings.
"""

from __future__ import annotations

import hmac

import streamlit as st

from shared.secrets import secret


def app_password() -> str | None:
    return secret("APP_PASSWORD")


def require_code(title: str = "Energy dashboard") -> None:
    password = app_password()
    if not password or st.session_state.get("app_unlocked"):
        return
    st.markdown(f"## {title}")
    code = st.text_input("Access code", type="password", key="app_code")
    if code:
        if hmac.compare_digest(code.encode(), password.encode()):
            st.session_state["app_unlocked"] = True
            st.rerun()
        st.error("That code isn't right.")
    st.stop()
