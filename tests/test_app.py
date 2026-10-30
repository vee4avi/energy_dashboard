"""Tests for the router, the home page, the access code and keeping filters between pages.

Run with:  python tests/test_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["COT_DEMO"] = "1"

from streamlit.testing.v1 import AppTest  # noqa: E402


def _router() -> AppTest:
    os.chdir(ROOT)
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)


def _text(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def test_registry() -> None:
    from modules.registry import MODULES

    keys = [m.key for m in MODULES]
    assert len(keys) == len(set(keys)), "section keys are url paths and must be unique"
    assert [m.key for m in MODULES if m.live] == ["cftc"]
    assert all(callable(m.render) for m in MODULES)
    print("registry: ok")


def test_app_opens_on_the_home_page() -> None:
    os.environ.pop("APP_PASSWORD", None)
    at = _router().run()
    assert not at.exception, [e.value for e in at.exception]
    text = _text(at)
    for box in ("Macro calendar", "Bank holidays", "Contract expiries"):
        assert box in text, box
    print("home page: ok")


def test_app_wide_access_code() -> None:
    os.environ["APP_PASSWORD"] = "open sesame"
    try:
        at = _router().run()
        assert not at.exception, [e.value for e in at.exception]
        assert at.text_input(key="app_code"), "the code box shows first"
        assert "Bank holidays" not in _text(at), "nothing is drawn before the code"

        at.text_input(key="app_code").input("wrong").run()
        assert any("isn't right" in e.value for e in at.error)
        at.text_input(key="app_code").input("open sesame").run()
        assert not at.exception, [e.value for e in at.exception]
        assert "Bank holidays" in _text(at), "unlocked"
    finally:
        os.environ.pop("APP_PASSWORD", None)
    print("access code: ok")


def test_filters_survive_a_visit_to_another_page() -> None:
    def script() -> None:
        import streamlit as st

        from shared import state

        state.remember()
        if st.session_state.get("_leave"):  # what Streamlit does to widgets not drawn this run
            st.session_state.pop("_leave")
            for key in ("pick", "flag"):
                st.session_state.pop(key, None)
            return
        st.selectbox("Pick", ["a", "b", "c"], key="pick")
        st.toggle("Flag", key="flag")
        st.button("Go", key="analysis_run")
        state.save()

    at = AppTest.from_function(script, default_timeout=30).run()
    at.selectbox(key="pick").set_value("c")
    at.toggle(key="flag").set_value(True).run()
    assert at.session_state["_kept__pick"] == "c"
    assert "_kept__analysis_run" not in at.session_state, "buttons are never copied"

    at.session_state["_leave"] = True  # a run on another page: the widgets are not drawn
    at.run()
    assert "pick" not in at.session_state, "Streamlit-style cleanup removed the widget value"

    at.run()  # back on the page
    assert at.selectbox(key="pick").value == "c" and at.toggle(key="flag").value is True
    print("filters kept between pages: ok")


if __name__ == "__main__":
    test_registry()
    test_app_opens_on_the_home_page()
    test_app_wide_access_code()
    test_filters_survive_a_visit_to_another_page()
    print("\nall app tests passed")
