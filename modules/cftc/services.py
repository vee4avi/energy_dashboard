"""Cached access to the data sources.

This is the only place Streamlit caching touches the data layer. When prices
and EIA storage arrive, give each its own ``load_*`` function here and keep
the sources themselves framework-free.

Two things happen here beyond plain fetching:

* **Implied options.** Nobody publishes an options-only COT. Asking for it
  loads both the combined and the futures-only report and subtracts.
* **ICE.** ICE Futures Europe rows come from ICE's own weekly PDFs and are
  concatenated onto the CFTC frame — same columns, same category keys.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.cftc.analytics import cot
from modules.cftc.config import settings
from modules.cftc.sources import cftc, commentary, demo, eia, ice
from shared.secrets import secret as _secret

DEMO_MODE = os.getenv("COT_DEMO", "").strip().lower() in {"1", "true", "yes"}

ICE_PREFIX = "ICE-"


def _is_ice(code: str) -> bool:
    return code.startswith(ICE_PREFIX)


def ice_supported(report: str) -> bool:
    return report == settings.ICE_ONLY_REPORT


def _source_basis(basis: str) -> str:
    """Which published report to read for a requested basis."""
    return "combined" if basis == settings.IMPLIED_OPTIONS_BASIS else basis


# --------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------
@st.cache_data(ttl=settings.CACHE_TTL_SECONDS, show_spinner=False)
def load_cftc_contracts(report: str, basis: str) -> pd.DataFrame:
    if DEMO_MODE:
        return demo.contracts(report)
    dataset = cftc.dataset_id(report, _source_basis(basis))
    columns = cftc.resolve_columns(dataset, report)
    return cftc.fetch_contracts(dataset, columns)


@st.cache_data(ttl=settings.CACHE_TTL_SECONDS, show_spinner=False)
def load_ice_contracts(basis: str) -> pd.DataFrame:
    """Never raises: ICE is an optional extra, so a failure just means no rows."""
    if DEMO_MODE:
        return demo.ice_contracts()
    try:
        return ice.catalog(_source_basis(basis))
    except (ice.IceDataError, OSError):
        return pd.DataFrame()


def load_contracts(report: str, basis: str, include_ice: bool = True) -> pd.DataFrame:
    """Every petroleum contract on offer, with its product group and where it came from."""
    catalog = load_cftc_contracts(report, basis)
    if include_ice and ice_supported(report):
        ice_catalog = load_ice_contracts(basis)
        if not ice_catalog.empty:
            catalog = pd.concat([catalog, ice_catalog], ignore_index=True)

    catalog = catalog.copy()
    catalog = _tag_source(catalog)
    if "group" not in catalog:
        catalog["group"] = None
    missing = catalog["group"].isna()
    if missing.any():
        catalog.loc[missing, "group"] = [
            settings.classify_product(name, code)
            for name, code in zip(
                catalog.loc[missing, "market_name"], catalog.loc[missing, "contract_code"]
            )
        ]
    for column, default in (("source", "—"), ("subgroup", "—")):
        if column not in catalog:
            catalog[column] = default
        catalog[column] = catalog[column].fillna(default)
    if "last_report" not in catalog:
        catalog["last_report"] = pd.NaT
    return catalog.sort_values("open_interest", ascending=False).reset_index(drop=True)


def _tag_source(catalog: pd.DataFrame) -> pd.DataFrame:
    """Mark each contract CFTC or ICE, and give ICE ones the " (ICE)" suffix.

    The rule is by data source, not by exchange: a contract the CFTC reports on
    an ICE venue is still CFTC data and keeps its plain name.
    """
    out = catalog.copy()
    is_ice = out["contract_code"].astype(str).str.startswith(ICE_PREFIX)
    out["data_source"] = is_ice.map({True: "ICE", False: "CFTC"})
    needs_suffix = is_ice & ~out["product"].astype(str).str.endswith(settings.ICE_SUFFIX)
    out.loc[needs_suffix, "product"] = out.loc[needs_suffix, "product"] + settings.ICE_SUFFIX
    return out


def group_options(catalog: pd.DataFrame) -> list[str]:
    """Product groups present in the catalog, in the configured order."""
    present = set(catalog["group"].dropna())
    ordered = [g for g in settings.GROUP_ORDER if g in present]
    return ordered + sorted(present - set(ordered))


# --------------------------------------------------------------------------
# Positions
# --------------------------------------------------------------------------
@st.cache_data(ttl=settings.CACHE_TTL_SECONDS, show_spinner=False)
def _load_cftc_positions(
    report: str, basis: str, contract_codes: tuple[str, ...], start: dt.date | None
) -> pd.DataFrame:
    if not contract_codes:
        return pd.DataFrame()
    if DEMO_MODE:
        frame = demo.positions(report)
        frame = frame[frame["contract_code"].isin(contract_codes)]
        if basis == "combined":
            frame = demo.scale(frame, 1.35)
        if start:
            frame = frame[frame["report_date"].ge(pd.Timestamp(start))]
        return frame.reset_index(drop=True)

    dataset = cftc.dataset_id(report, basis)
    columns = cftc.resolve_columns(dataset, report)
    return cftc.fetch_positions(dataset, columns, list(contract_codes), start)


@st.cache_data(ttl=settings.CACHE_TTL_SECONDS, show_spinner=False)
def _load_ice_positions(
    basis: str, contract_codes: tuple[str, ...], start: dt.date | None
) -> pd.DataFrame:
    if not contract_codes:
        return pd.DataFrame()
    if DEMO_MODE:
        frame = demo.ice_positions()
        frame = frame[frame["contract_code"].isin(contract_codes)]
        if basis == "combined":
            frame = demo.scale(frame, 1.4)
        if start:
            frame = frame[frame["report_date"].ge(pd.Timestamp(start))]
        return frame.reset_index(drop=True)
    try:
        return ice.load_history(list(contract_codes), basis, start)
    except (ice.IceDataError, OSError):
        return pd.DataFrame()


def _load_basis(
    report: str,
    basis: str,
    cftc_codes: tuple[str, ...],
    ice_codes: tuple[str, ...],
    start: dt.date | None,
) -> pd.DataFrame:
    frames = [
        _load_cftc_positions(report, basis, cftc_codes, start),
        _load_ice_positions(basis, ice_codes, start),
    ]
    frames = [frame for frame in frames if not frame.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_positions(
    report: str, basis: str, contract_codes: tuple[str, ...], start: dt.date | None
) -> pd.DataFrame:
    cftc_codes = tuple(code for code in contract_codes if not _is_ice(code))
    ice_codes = tuple(code for code in contract_codes if _is_ice(code))

    if basis != settings.IMPLIED_OPTIONS_BASIS:
        frame = _load_basis(report, basis, cftc_codes, ice_codes, start)
    else:
        combined = _load_basis(report, "combined", cftc_codes, ice_codes, start)
        futures = _load_basis(report, "futures_only", cftc_codes, ice_codes, start)
        frame = cot.implied_options(combined, futures)
    return _attach_catalog_fields(frame, report, basis)


def _attach_catalog_fields(frame: pd.DataFrame, report: str, basis: str) -> pd.DataFrame:
    """Use the catalog's label and group so a product has one name everywhere."""
    if frame.empty:
        return frame
    catalog = load_contracts(report, basis, include_ice=True).drop_duplicates("contract_code")
    labels = catalog.set_index("contract_code")["product"]
    groups = catalog.set_index("contract_code")["group"]
    sources = catalog.set_index("contract_code")["data_source"]
    out = frame.copy()
    out["data_source"] = out["contract_code"].map(sources).fillna(
        out["contract_code"].astype(str).str.startswith(ICE_PREFIX).map({True: "ICE", False: "CFTC"})
    )
    out["product"] = out["contract_code"].map(labels).fillna(out["product"])
    out["group"] = out["contract_code"].map(groups).fillna(
        pd.Series(
            [settings.classify_product(m, c) for m, c in zip(out["market_name"], out["contract_code"])],
            index=out.index,
        )
    )
    return out


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
COMMENTARY_DIR = Path(__file__).resolve().parents[2] / "commentary"


def commentary_source() -> str:
    """Where saved commentary is looked for, in words, for on-screen hints."""
    return "the commentary folder"


@st.cache_data(ttl=600, show_spinner=False)
def load_commentary() -> tuple[dict, str]:
    """Weekly commentary keyed by report date, plus a note if it could not be read.

    The only source is the ``commentary`` folder next to ``app.py``, filled with the
    bot's JSON files. Nothing is fetched and no secret is needed.
    """
    if DEMO_MODE:
        return demo.commentary(), ""
    return commentary.load_folder(COMMENTARY_DIR, settings.COMMENTARY_MAX_FILES), ""


# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# EIA storage
# --------------------------------------------------------------------------
def eia_key() -> str | None:
    return _secret("EIA_API_KEY")


def eia_available() -> bool:
    return DEMO_MODE or bool(eia_key())


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _load_storage(key: str, start: str) -> pd.DataFrame:
    if DEMO_MODE:
        return demo.storage()
    return eia.fetch(key, start)


def load_storage(start: str = "1982-01-01") -> pd.DataFrame:
    """Weekly US stocks. Raises ``eia.EiaError`` (safe to show) when unavailable."""
    key = eia_key()
    if not key and not DEMO_MODE:
        raise eia.EiaError("No EIA_API_KEY is set.")
    return _load_storage(key or "demo", start)


def start_date_for(window_label: str) -> dt.date | None:
    years = settings.HISTORY_WINDOWS.get(window_label)
    if years is None:
        return None
    today = dt.date.today()
    return today.replace(year=today.year - years)


def clear_cache() -> None:
    for cached in (
        load_cftc_contracts,
        load_ice_contracts,
        _load_cftc_positions,
        _load_ice_positions,
        load_commentary,
        _load_storage,
    ):
        cached.clear()


def next_release(today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    """Upcoming publication (Friday) and the Tuesday it will cover."""
    today = today or dt.date.today()
    days_ahead = (4 - today.weekday()) % 7  # Friday = 4
    friday = today + dt.timedelta(days=days_ahead)
    return friday, friday - dt.timedelta(days=3)
