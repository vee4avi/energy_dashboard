"""The CFTC positioning module: one page with its own sidebar filters and tabs."""

from __future__ import annotations

import datetime as dt

import pandas as pd
import streamlit as st

from modules.cftc import services
from modules.cftc.analytics import cot
from modules.cftc.config import settings
from modules.cftc.sources.cftc import CftcDataError
from modules.cftc.ui import filters as filters_ui
from modules.cftc.ui import views
from shared import state


def header(loaded: pd.DataFrame, basis: str, ice_missing: bool) -> None:
    as_of = loaded["report_date"].max() if not loaded.empty else None
    columns = st.columns([4, 2, 2, 2])
    columns[0].markdown(f"## {settings.META.title}")

    stale = None
    if as_of is not None:
        stale = (dt.date.today() - as_of.date()).days
        columns[1].metric(
            "Positions as of", f"{as_of:%d %b %Y}", f"{stale} days ago", delta_color="off"
        )
        release, covers = services.next_release()
        columns[2].metric(
            "Next release", f"{release:%a %d %b}", f"covers {covers:%d %b}", delta_color="off"
        )
    columns[3].metric(
        "Contracts tracked", f"{loaded['product'].nunique() if not loaded.empty else 0}"
    )

    if stale is not None and stale > 12:
        st.warning(
            f"Latest CFTC report is {stale} days old — publication may be delayed.",
            icon="🕓",
        )

    if basis == settings.IMPLIED_OPTIONS_BASIS:
        st.info(settings.IMPLIED_OPTIONS_NOTE, icon="🧮")

    if ice_missing:
        st.caption(
            "ICE Futures Europe is selected but no ICE contracts loaded — "
            "ice.com could not be reached, or the report layout changed."
        )

    if services.DEMO_MODE:
        st.warning(
            "Demo mode: figures are synthetic. Unset COT_DEMO to read live CFTC data.",
            icon="⚠️",
        )


def render() -> None:
    """The page. Filter values are kept when you visit another page and come back."""
    state.remember()
    try:
        _render()
    finally:  # also runs when the page stops early (st.stop), so nothing is lost
        state.save()


def _render() -> None:
    try:
        report = st.session_state.get("report", "disaggregated")
        catalog = services.load_contracts(
            report,
            st.session_state.get("basis", "futures_only"),
            include_ice=services.ice_supported(report)
            and ("ICE" in (st.session_state.get("sources") or ["ICE"])),
        )
    except CftcDataError as error:
        st.error(str(error))
        st.caption(
            "Check the network can reach publicreporting.cftc.gov, or run with "
            "COT_DEMO=1 to preview the dashboard with synthetic data."
        )
        st.stop()

    active = filters_ui.render(catalog)

    if not active.contract_codes:
        st.info("Pick at least one product in the sidebar.")
        st.stop()
    if not active.categories:
        st.info("Pick at least one trader category in the sidebar.")
        st.stop()

    with st.spinner("Loading positioning history…"):
        try:
            raw = services.load_positions(
                active.report,
                active.basis,
                tuple(active.contract_codes),
                services.start_date_for(active.history_window),
            )
        except CftcDataError as error:
            st.error(str(error))
            st.stop()

    if raw.empty:
        st.warning("The CFTC returned no rows for that selection.")
        st.stop()

    enriched = cot.enrich(raw, lookback=active.lookback)

    ice_missing = (
        active.include_ice
        and services.ice_supported(active.report)
        and not catalog["data_source"].eq("ICE").any()
    )
    header(enriched, active.basis, ice_missing)
    st.divider()

    tabs = st.tabs(list(settings.META.tabs))
    with tabs[0]:
        views.snapshot_tab(enriched, active)
    with tabs[1]:
        views.compare_tab(enriched, active)
    with tabs[2]:
        views.full_table_tab(enriched, active)
    with tabs[3]:
        views.breakdown_tab(enriched, active)
    with tabs[4]:
        views.storage_tab(enriched, active)
    with tabs[5]:
        views.data_tab(enriched, active, catalog)

    st.caption(
        f"Positions are as of Tuesday close. {settings.META.release_note} "
        f"Source: {settings.META.source_url}"
    )
