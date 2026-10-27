"""Synthetic COT data.

Used when ``COT_DEMO=1`` so the dashboard can be opened (and tested) without
reaching the CFTC API — handy on a locked-down network or for UI work.
The shape matches exactly what ``sources.cftc`` returns.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from modules.cftc.config import settings
from modules.cftc.sources.commentary import Commentary

_PRODUCTS = [
    ("067651", "WTI Crude", "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE", "NYME", 1_850_000),
    ("06765T", "Brent Last Day Nymex", "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE", "NYME", 310_000),
    ("111659", "RBOB Gasoline", "GASOLINE RBOB - NEW YORK MERCANTILE EXCHANGE", "NYME", 340_000),
    ("022651", "NY ULSD", "NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE", "NYME", 290_000),
    ("02265A", "Gasoil", "GASOIL - ICE FUTURES ENERGY DIV", "ICEU", 180_000),
    ("06665A", "WTI Nymex", "WTI FINANCIAL CRUDE OIL - NEW YORK MERCANTILE EXCHANGE", "NYME", 95_000),
    ("DEMO01", "WTI Physical Nymex", "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE", "NYME", 1_880_000),
    ("DEMO02", "Jet Fuel, NY", "JET FUEL, NY - NEW YORK MERCANTILE EXCHANGE", "NYME", 42_000),
    ("DEMO03", "Fuel Oil, NYH 1%", "FUEL OIL, NYH 1% - NEW YORK MERCANTILE EXCHANGE", "NYME", 38_000),
    ("DEMO04", "Fuel Oil Crack", "FUEL OIL CRACK - NEW YORK MERCANTILE EXCHANGE", "NYME", 24_000),
    ("DEMO05", "WCS Houston/WTI 1st Line", "WCS HOUSTON/WTI 1ST LINE - NEW YORK MERCANTILE EXCHANGE", "NYME", 16_000),
    ("DEMO06", "Gulf Jet NY Heat Oil Spr", "GULF JET NY HEAT OIL SPR - NEW YORK MERCANTILE EXCHANGE", "NYME", 9_500),
]

_MIX = {
    "m_money": (0.22, 0.07),
    "noncomm": (0.24, 0.09),
    "comm": (0.48, 0.66),
    "prod_merc": (0.28, 0.42),
    "swap": (0.20, 0.24),
    "other_rept": (0.12, 0.10),
    "nonrept": (0.08, 0.07),
    "tot_rept": (0.82, 0.83),
}


def _weeks(years: int = 6) -> pd.DatetimeIndex:
    end = pd.Timestamp(dt.date.today()) - pd.Timedelta(days=5)
    end = end - pd.Timedelta(days=(end.weekday() - 1) % 7)  # last Tuesday
    return pd.date_range(end=end, periods=int(years * 52), freq="7D")


def positions(report: str = "disaggregated") -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = _weeks()
    rows = []
    for code, product, market, exchange, base_oi in _PRODUCTS:
        drift = np.cumsum(rng.normal(0, 0.012, len(dates)))
        oi = base_oi * (1 + 0.12 * np.sin(np.linspace(0, 8, len(dates))) + drift / 4)
        for key, (long_share, short_share) in _MIX.items():
            if key not in {c.key for c in settings.categories_for(report)}:
                continue
            wobble = np.cumsum(rng.normal(0, 0.02, len(dates)))
            long_leg = oi * long_share * (1 + 0.25 * np.sin(np.linspace(0, 5, len(dates))) + wobble / 3)
            short_leg = oi * short_share * (1 - 0.18 * np.sin(np.linspace(1, 6, len(dates))) + wobble / 4)
            rows.append(
                pd.DataFrame(
                    {
                        "report_date": dates,
                        "contract_code": code,
                        "market_name": market,
                        "contract_name": product,
                        "exchange": exchange,
                        "open_interest": np.round(oi),
                        "category": key,
                        "long": np.round(np.clip(long_leg, 0, None)),
                        "short": np.round(np.clip(short_leg, 0, None)),
                        "spread": np.round(np.clip(oi * 0.05 * (1 + wobble / 5), 0, None)),
                        "product": product,
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def contracts(report: str = "disaggregated") -> pd.DataFrame:
    frame = positions(report)
    as_of = frame["report_date"].max()
    latest = frame[frame["report_date"].eq(as_of)]
    out = (
        latest.groupby(["contract_code", "product", "market_name", "exchange"], as_index=False)
        .agg(open_interest=("open_interest", "max"))
        .sort_values("open_interest", ascending=False)
        .reset_index(drop=True)
    )
    out["contract_name"] = out["product"]
    out["subgroup"] = settings.PETROLEUM_SUBGROUP
    out["source"] = "Demo data"
    out["last_report"] = as_of
    out["as_of"] = as_of.date()
    return out


_ICE_PRODUCTS = [
    ("ICE-B", "Brent (ICE)", "ICE BRENT CRUDE FUTURES - ICE FUTURES EUROPE", 2_400_000),
    ("ICE-G", "Gasoil (ICE)", "ICE GASOIL FUTURES - ICE FUTURES EUROPE", 1_050_000),
]


def ice_positions() -> pd.DataFrame:
    """Synthetic stand-in for the ICE Futures Europe reports."""
    rng = np.random.default_rng(11)
    dates = _weeks()
    rows = []
    for code, product, market, base_oi in _ICE_PRODUCTS:
        drift = np.cumsum(rng.normal(0, 0.011, len(dates)))
        oi = base_oi * (1 + 0.10 * np.cos(np.linspace(0, 7, len(dates))) + drift / 4)
        for key, (long_share, short_share) in _MIX.items():
            if key in {"noncomm", "comm"}:
                continue
            wobble = np.cumsum(rng.normal(0, 0.02, len(dates)))
            long_leg = oi * long_share * (1 + 0.22 * np.cos(np.linspace(0, 4, len(dates))) + wobble / 3)
            short_leg = oi * short_share * (1 - 0.15 * np.cos(np.linspace(2, 6, len(dates))) + wobble / 4)
            rows.append(
                pd.DataFrame(
                    {
                        "report_date": dates,
                        "contract_code": code,
                        "market_name": market,
                        "contract_name": product,
                        "exchange": "IFEU",
                        "open_interest": np.round(oi),
                        "category": key,
                        "long": np.round(np.clip(long_leg, 0, None)),
                        "short": np.round(np.clip(short_leg, 0, None)),
                        "spread": np.round(np.clip(oi * 0.06 * (1 + wobble / 5), 0, None)),
                        "product": product,
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def ice_contracts() -> pd.DataFrame:
    frame = ice_positions()
    latest = frame[frame["report_date"].eq(frame["report_date"].max())]
    out = (
        latest.groupby(
            ["contract_code", "product", "market_name", "exchange"], as_index=False
        )
        .agg(open_interest=("open_interest", "max"))
        .sort_values("open_interest", ascending=False)
        .reset_index(drop=True)
    )
    out["contract_name"] = out["product"]
    out["subgroup"] = settings.PETROLEUM_SUBGROUP
    out["source"] = "Demo data"
    out["last_report"] = latest["report_date"].max()
    out["as_of"] = latest["report_date"].max().date()
    return out


def scale(frame: pd.DataFrame, factor: float) -> pd.DataFrame:
    """Rough stand-in for the combined report — bigger book, same shape."""
    out = frame.copy()
    for column in ("long", "short", "spread", "open_interest"):
        out[column] = np.round(out[column] * factor)
    return out


def commentary() -> dict[pd.Timestamp, Commentary]:
    """A placeholder weekly commentary for the latest demo week, so the panel can be previewed."""
    latest = _weeks()[-1].normalize()
    record = Commentary(
        report_date=latest,
        prior_date=latest - pd.Timedelta(days=7),
        text=(
            "# DEMO COMMENTARY: not real analysis\n\n"
            "## 🔑 Key Positioning Shifts\n"
            "Managed money added to net length in crude while products were flat.\n\n"
            "## ⚖️ Physical vs Financial\n"
            "Producers hedged into the move.\n\n"
            "## 🌐 Macro & Fundamentals\n"
            "Placeholder text for layout preview. Prices of $114 and $135 test the dollar signs.\n\n"
            "## ⚡ Risk Outlook\n"
            "Placeholder text for layout preview."
        ),
        news="Demo mode: no news was searched.",
        basis="combined",
        generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        model="demo",
        products=("WTI Crude", "Brent Last Day Nymex"),
        origin="demo",
    )
    return {record.report_date: record}


def storage() -> pd.DataFrame:
    """Synthetic weekly stocks with a seasonal swing, for ``COT_DEMO=1``."""

    end = pd.Timestamp(dt.date.today())
    end = end - pd.Timedelta(days=(end.weekday() - 4) % 7)  # last Friday
    weeks = pd.date_range(end=end, periods=9 * 52, freq="7D")
    base = {"Crude (commercial)": (440, 25), "Cushing crude": (30, 8), "SPR": (400, 15),
            "Gasoline": (230, 12), "Distillate": (125, 10), "Jet fuel": (40, 3), "Natural gas": (2800, 700)}
    rng = np.random.default_rng(7)
    rows = []
    for name, (level, swing) in base.items():
        phase = 0.0 if name != "Natural gas" else 2.2
        wave = level + swing * np.sin(2 * np.pi * weeks.dayofyear / 365 + phase)
        wave = wave + np.cumsum(rng.normal(0, swing * 0.04, len(weeks)))
        rows += [(w, name, float(v)) for w, v in zip(weeks, wave)]
    return pd.DataFrame(rows, columns=["period", "series", "value"])
