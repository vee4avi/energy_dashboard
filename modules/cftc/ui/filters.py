"""Sidebar controls."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from modules.cftc import services
from modules.cftc.config import settings
from shared import state, theme


@dataclass
class Filters:
    report: str
    basis: str
    sources: list[str]
    groups: list[str]
    contract_codes: list[str]
    categories: list[str]
    unit: str
    history_window: str
    lookback: int

    @property
    def include_ice(self) -> bool:
        return "ICE" in self.sources

    @property
    def value_column(self) -> str:
        return settings.UNITS[self.unit]

    @property
    def change_column(self) -> str:
        return "net_pct_oi_chg_1w" if self.unit.startswith("%") else "net_chg_1w"


def _format_product(code: str, catalog: pd.DataFrame) -> str:
    row = catalog.loc[catalog["contract_code"].eq(code)]
    return code if row.empty else str(row.iloc[0]["product"])


def _chips(label: str, options: list[str], key: str, help_text: str) -> list[str]:
    """Multi-select chips (falls back to a multiselect on older Streamlit)."""
    state.prune_multiselect(key, options)
    pills = getattr(st.sidebar, "pills", None)
    if pills is not None:
        return list(
            pills(label, options=options, selection_mode="multi", key=key, help=help_text)
            or []
        )
    return st.sidebar.multiselect(label, options=options, key=key, help=help_text)


def render(catalog: pd.DataFrame) -> Filters:
    st.sidebar.markdown("### Filters")
    ice_supported = st.session_state.get("report", "disaggregated") == settings.ICE_ONLY_REPORT

    report = st.sidebar.selectbox(
        "Report",
        options=list(settings.REPORT_LABELS),
        format_func=lambda key: settings.REPORT_LABELS[key],
        key="report",
        help="Disaggregated (standard for energy): Producer/merchant, Swap dealers, "
        "Managed money, Other reportables. Legacy: just Commercial vs Non-commercial "
        "- swap dealers sit inside commercial and funds inside non-commercial, so the "
        "two groups are blurrier, but the history reaches back much further. "
        "ICE publishes no legacy report.",
    )
    basis = st.sidebar.selectbox(
        "Basis",
        options=list(settings.BASIS_LABELS),
        format_func=lambda key: settings.BASIS_LABELS[key],
        key="basis",
        help="Combined adds delta-adjusted options to the futures book. "
        "Options only is derived by subtracting one from the other.",
    )
    if basis == settings.IMPLIED_OPTIONS_BASIS:
        st.sidebar.caption(settings.IMPLIED_OPTIONS_NOTE)

    if ice_supported:
        chosen = _chips(
            "Data source",
            list(settings.SOURCE_OPTIONS),
            "sources",
            "CFTC: the CFTC's weekly report. ICE: ICE Futures Europe's own report "
            "(Brent, Gasoil), shown with (ICE) after the name. Leave empty for both. "
            "ICE is fetched from weekly PDFs, then cached.",
        )
        sources = chosen or list(settings.SOURCE_OPTIONS)
    else:
        sources = ["CFTC"]
        st.sidebar.caption(
            "ICE Futures Europe publishes no legacy-format report, so only CFTC data is shown."
        )

    st.sidebar.divider()

    group_choices = services.group_options(catalog)
    groups = _chips(
        "Product group",
        group_choices,
        "groups",
        "Narrows the product list below. Leave empty to see everything. "
        "Groups are assigned by contract name — see config/settings.py.",
    )
    active_groups = groups or group_choices

    universe = catalog[
        catalog["group"].isin(active_groups) & catalog["data_source"].isin(sources)
    ]
    codes = universe["contract_code"].tolist()  # already largest open interest first
    default_codes = codes[: settings.DEFAULT_PRODUCT_COUNT]

    # Re-default the selection when the universe changes (group, report, basis,
    # ICE on/off) — otherwise the old picks would simply vanish and leave it empty.
    signature = (
        report,
        basis,
        tuple(sources),
        tuple(active_groups),
    )
    kept = [c for c in st.session_state.get("products", []) if c in codes]
    if "products" not in st.session_state or st.session_state.get("_products_for") != signature:
        st.session_state["products"] = kept or default_codes
        st.session_state["_products_for"] = signature
    else:
        st.session_state["products"] = kept

    contract_codes = st.sidebar.multiselect(
        "Products",
        options=codes,
        format_func=lambda code: _format_product(code, catalog),
        key="products",
        help="Pick one or many; largest open interest first. "
        "Everything on the page updates together.",
    )
    st.sidebar.caption(
        f"{len(codes)} contracts in this view."
        if codes
        else "No contracts match this combination of filters."
    )

    category_options = settings.categories_for(report)
    labels = {c.key: c.ui_label for c in category_options}
    state.prune_multiselect(f"categories_{report}", [c.key for c in category_options])
    categories = st.sidebar.multiselect(
        "Trader categories",
        options=[c.key for c in category_options],
        default=settings.default_categories(report),
        format_func=lambda key: labels[key],
        key=f"categories_{report}",
    )

    st.sidebar.divider()

    unit = st.sidebar.radio(
        "Units",
        options=list(settings.UNITS),
        key="unit",
        horizontal=True,
        help="Percent of open interest makes products of different size comparable.",
    )
    history_window = st.sidebar.selectbox(
        "History to load",
        options=list(settings.HISTORY_WINDOWS),
        index=list(settings.HISTORY_WINDOWS).index(settings.DEFAULT_HISTORY_WINDOW),
        key="history",
        help="Also sets how far back charts and date pickers can reach.",
    )
    lookback = st.sidebar.slider(
        "Z-score / COT index window (weeks)",
        min_value=52,
        max_value=520,
        value=settings.DEFAULT_LOOKBACK_WEEKS,
        step=26,
        key="lookback",
    )

    st.sidebar.divider()
    if st.sidebar.button("Refresh data", **theme.wide()):
        from modules.cftc.services import clear_cache

        clear_cache()
        st.rerun()

    st.sidebar.caption(
        f"Source: CFTC Public Reporting Environment. {settings.META.release_note}"
    )

    return Filters(
        report=report,
        basis=basis,
        sources=sources,
        groups=groups,
        contract_codes=contract_codes,
        categories=categories,
        unit=unit,
        history_window=history_window,
        lookback=lookback,
    )
