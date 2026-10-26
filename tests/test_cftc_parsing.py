"""Offline tests for the CFTC parsing layer.

The Socrata column names carry historical quirks (``swap__positions_short_all``
has a double underscore, ``_all`` suffixes are inconsistent, and old/other crop
year variants sit next to the ones we want). These tests pin the resolver
against a realistic column list so a schema change fails loudly instead of
silently mapping the wrong leg.

Run with:  python -m pytest tests -q     (or: python tests/test_cftc_parsing.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.cftc.sources import cftc  # noqa: E402

DISAGGREGATED_COLUMNS = [
    "market_and_exchange_names",
    "report_date_as_yyyy_mm_dd",
    "yyyy_report_week_ww",
    "contract_market_name",
    "cftc_contract_market_code",
    "cftc_market_code",
    "cftc_region_code",
    "cftc_commodity_code",
    "commodity_name",
    "commodity_subgroup_name",
    "commodity_group_name",
    "open_interest_all",
    "prod_merc_positions_long",
    "prod_merc_positions_short",
    "prod_merc_positions_long_old",
    "prod_merc_positions_short_other",
    "swap_positions_long_all",
    "swap__positions_short_all",
    "swap__positions_spread_all",
    "m_money_positions_long_all",
    "m_money_positions_short_all",
    "m_money_positions_spread",
    "other_rept_positions_long",
    "other_rept_positions_short",
    "other_rept_positions_spread",
    "tot_rept_positions_long_all",
    "tot_rept_positions_short",
    "nonrept_positions_long_all",
    "nonrept_positions_short_all",
    "change_in_open_interest_all",
    "change_in_m_money_long_all",
    "change_in_m_money_short_all",
    "pct_of_open_interest_all",
    "pct_of_oi_m_money_long_all",
    "traders_m_money_long_all",
    "conc_gross_le_4_tdr_long",
]

EXPECTED_SIDES = {
    "m_money": ("m_money_positions_long_all", "m_money_positions_short_all", "m_money_positions_spread"),
    "prod_merc": ("prod_merc_positions_long", "prod_merc_positions_short", None),
    "swap": ("swap_positions_long_all", "swap__positions_short_all", "swap__positions_spread_all"),
    "other_rept": ("other_rept_positions_long", "other_rept_positions_short", "other_rept_positions_spread"),
    "nonrept": ("nonrept_positions_long_all", "nonrept_positions_short_all", None),
    "tot_rept": ("tot_rept_positions_long_all", "tot_rept_positions_short", None),
}


def _mock_row(columns: list[str]) -> dict:
    return {column: "1" for column in columns}


def test_resolve_columns(monkeypatch=None) -> None:
    cftc.list_columns = lambda dataset_id: DISAGGREGATED_COLUMNS  # type: ignore[assignment]
    columns = cftc.resolve_columns("72hh-3qpy", "disaggregated")

    assert columns.date == "report_date_as_yyyy_mm_dd"
    assert columns.open_interest == "open_interest_all"
    assert columns.subgroup == "commodity_subgroup_name"

    for key, (long_leg, short_leg, spread) in EXPECTED_SIDES.items():
        legs = columns.sides[key]
        assert legs["long"] == long_leg, (key, legs["long"])
        assert legs["short"] == short_leg, (key, legs["short"])
        if spread:
            assert legs["spread"] == spread, (key, legs["spread"])

    # No change/pct/trader/concentration column ever leaks into a position leg.
    selected = columns.select_fields()
    assert not [c for c in selected if c.startswith(("change_in", "pct_of", "traders_", "conc_"))]
    # Old and other crop-year variants are excluded.
    assert "prod_merc_positions_long_old" not in selected
    assert "prod_merc_positions_short_other" not in selected
    print("resolve_columns: ok —", len(selected), "fields selected")


def test_tidy_shape() -> None:
    cftc.list_columns = lambda dataset_id: DISAGGREGATED_COLUMNS  # type: ignore[assignment]
    columns = cftc.resolve_columns("72hh-3qpy", "disaggregated")

    wide = pd.DataFrame(
        [
            {
                **_mock_row(DISAGGREGATED_COLUMNS),
                "report_date_as_yyyy_mm_dd": "2026-09-15T00:00:00.000",
                "market_and_exchange_names": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
                "contract_market_name": "CRUDE OIL, LIGHT SWEET",
                "cftc_contract_market_code": "067651",
                "cftc_market_code": "NYME",
                "open_interest_all": "1850000",
                "m_money_positions_long_all": "250000",
                "m_money_positions_short_all": "120000",
            },
            {
                **_mock_row(DISAGGREGATED_COLUMNS),
                "report_date_as_yyyy_mm_dd": "2026-09-15T00:00:00.000",
                "market_and_exchange_names": "GASOLINE RBOB - NEW YORK MERCANTILE EXCHANGE",
                "contract_market_name": "GASOLINE RBOB",
                "cftc_contract_market_code": "111659",
                "cftc_market_code": "NYME",
                "open_interest_all": "340000",
                "m_money_positions_long_all": "80000",
                "m_money_positions_short_all": "20000",
            },
        ]
    )

    tidy = cftc.tidy(wide, columns)
    assert set(tidy["product"]) == {"Crude Oil, Light Sweet", "Gasoline RBOB"}
    assert len(tidy) == 2 * len(columns.sides)
    wti = tidy[(tidy["product"] == "Crude Oil, Light Sweet") & (tidy["category"] == "m_money")].iloc[0]
    assert wti["long"] == 250000 and wti["short"] == 120000
    assert pd.api.types.is_datetime64_any_dtype(tidy["report_date"])
    print("tidy: ok —", len(tidy), "rows")


def test_pretty_names() -> None:
    """Labels come from the contract's own name, so distinct contracts stay distinct."""
    cases = [
        ("WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE", None, "WTI Physical Nymex"),
        ("WTI FINANCIAL CRUDE OIL - NEW YORK MERCANTILE EXCHANGE", None, "WTI Nymex"),
        ("CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE", None, "WTI Ice EU"),
        ("WTI CRUDE OIL 1ST LINE - ICE FUTURES EUROPE", None, "WTI 1st line Ice Futures"),
        ("WTI 1ST LINE - ICE FUTURES ENERGY DIV", None, "WTI 1st line Ice Futures"),
        ("BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE", "BRENT LAST DAY", "Brent Last Day Nymex"),
        # no rule: NYMEX light sweet is a different contract from the ICE one
        ("CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE", "CRUDE OIL, LIGHT SWEET", "Crude Oil, Light Sweet"),
        ("NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE", "NY HARBOR ULSD", "NY Harbor ULSD"),
        ("WCS HOUSTON/WTI 1ST LINE - NEW YORK MERCANTILE EXCHANGE", None, "WCS Houston/WTI 1st Line"),
    ]
    for market, contract, expected in cases:
        assert cftc.pretty_name(market, contract, "NYME") == expected, (market, expected)

    # The bug being fixed: two different RBOB contracts used to share one label.
    plain = cftc.pretty_name("GASOLINE RBOB - NYMEX", "GASOLINE RBOB", "NYME")
    crack = cftc.pretty_name("RBOB GASOLINE CRACK SPREAD - NYMEX", "RBOB GASOLINE CRACK SPREAD", "NYME")
    assert plain != crack, (plain, crack)
    print("pretty_name: ok")


def test_disambiguate_only_when_names_collide() -> None:
    unique = pd.DataFrame(
        {"product": ["A", "B"], "exchange": ["NYME", "NYME"], "contract_code": ["1", "2"]}
    )
    assert cftc._disambiguate(unique)["product"].tolist() == ["A", "B"]

    clash = pd.DataFrame(
        {"product": ["Brent", "Brent"], "exchange": ["NYME", "ICEU"], "contract_code": ["1", "2"]}
    )
    assert cftc._disambiguate(clash)["product"].tolist() == ["Brent (NYME)", "Brent (ICEU)"]

    twins = pd.DataFrame(
        {"product": ["X", "X"], "exchange": ["NYME", "NYME"], "contract_code": ["a", "b"]}
    )
    labels = cftc._disambiguate(twins)["product"].tolist()
    assert len(set(labels)) == 2 and labels[0].endswith("[a]"), labels
    print("disambiguate: ok")


def test_group_classification() -> None:
    from modules.cftc.config import settings

    cases = {
        "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE": "Crude",
        "BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE": "Crude",
        "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE": "Crude",
        "GASOLINE RBOB - NEW YORK MERCANTILE EXCHANGE": "Products",
        "NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE": "Products",
        "JET FUEL, NY - NEW YORK MERCANTILE EXCHANGE": "Products",
        "FUEL OIL, NYH 1% - NEW YORK MERCANTILE EXCHANGE": "Products",
        "WCS HOUSTON/WTI 1ST LINE - NEW YORK MERCANTILE EXCHANGE": "Spreads",
        "FUEL OIL CRACK - NEW YORK MERCANTILE EXCHANGE": "Spreads",
        "GULF JET NY HEAT OIL SPR - NEW YORK MERCANTILE EXCHANGE": "Spreads",
        "USGC HSFO (PLATTS) - NEW YORK MERCANTILE EXCHANGE": "Products",
        "SINGAPORE VLSFO - NEW YORK MERCANTILE EXCHANGE": "Products",
        "MARINE 0.5% FOB USGC - NEW YORK MERCANTILE EXCHANGE": "Products",
        "USGC HSFO VS BRENT - NEW YORK MERCANTILE EXCHANGE": "Spreads",
        "ICE BRENT CRUDE FUTURES - ICE FUTURES EUROPE": "Crude",
        "ICE GASOIL FUTURES - ICE FUTURES EUROPE": "Products",
        "SOMETHING ELSE ENTIRELY - SOME EXCHANGE": "Other",
    }
    for market, expected in cases.items():
        assert settings.classify_product(market) == expected, (market, settings.classify_product(market))

    # The exchange name must never drive the group.
    assert settings.contract_part("A/B CONTRACT - SOME/ODD EXCHANGE") == "A/B CONTRACT"
    # Overrides win.
    settings.GROUP_OVERRIDES["XYZ"] = "Spreads"
    try:
        assert settings.classify_product("WTI-PHYSICAL - NYMEX", "XYZ") == "Spreads"
    finally:
        settings.GROUP_OVERRIDES.pop("XYZ")
    print("group classification: ok")


def test_fetch_contracts_window_dedupe_and_source() -> None:
    """fetch_contracts against a mocked Socrata response."""
    cftc.list_columns = lambda dataset_id: DISAGGREGATED_COLUMNS  # type: ignore[assignment]
    columns = cftc.resolve_columns("72hh-3qpy", "disaggregated")

    def row(date, code, market, contract, oi, subgroup="PETROLEUM AND PRODUCTS"):
        return {
            "report_date_as_yyyy_mm_dd": f"{date}T00:00:00.000",
            "cftc_contract_market_code": code,
            "market_and_exchange_names": market,
            "contract_market_name": contract,
            "cftc_market_code": "NYME",
            "commodity_subgroup_name": subgroup,
            "open_interest_all": str(oi),
        }

    served = {}

    def fake_get(dataset_id, params, retries=3):
        served["params"] = params
        if "max(" in params.get("$select", ""):
            return [{"latest": "2026-09-29T00:00:00.000"}]
        return [
            row("2026-09-29", "067651", "WTI-PHYSICAL - NYMEX", "WTI-PHYSICAL", 1_878_576),
            row("2026-09-22", "067651", "WTI-PHYSICAL - NYMEX", "WTI-PHYSICAL", 1_850_000),
            row("2026-09-29", "111659", "GASOLINE RBOB - NYMEX", "GASOLINE RBOB", 340_000),
            row("2026-09-29", "111A34", "RBOB GASOLINE CRACK SPREAD - NYMEX", "RBOB GASOLINE CRACK SPREAD", 3_100),
            # skipped the latest week, still inside the window -> must stay
            row("2026-09-15", "86465A", "FUEL OIL CRACK - NYMEX", "FUEL OIL CRACK", 900),
            # filed under another subgroup, found by the name sweep
            row("2026-09-29", "06765W", "WCS HOUSTON/WTI 1ST LINE - NYMEX", "WCS HOUSTON/WTI 1ST LINE", 14_000,
                subgroup="NATURAL GAS AND PRODUCTS"),
        ]

    original = cftc._get
    cftc._get = fake_get  # type: ignore[assignment]
    try:
        out = cftc.fetch_contracts("72hh-3qpy", columns)
    finally:
        cftc._get = original  # type: ignore[assignment]

    assert len(out) == 5, out[["product"]]
    assert out["contract_code"].is_unique, "one row per contract"
    # latest print wins, not an older one
    assert out.set_index("contract_code").loc["067651", "open_interest"] == 1_878_576
    # tiny and stale contracts are NOT filtered out any more
    assert {"111A34", "86465A"} <= set(out["contract_code"])
    # the two RBOB contracts have different labels (no '#code' tags needed)
    labels = out.set_index("contract_code")["product"]
    assert labels["111659"] != labels["111A34"]
    assert not out["product"].str.contains("#").any()
    # groups and provenance
    groups = out.set_index("contract_code")["group"]
    assert groups["067651"] == "Crude" and groups["111659"] == "Products"
    assert groups["111A34"] == "Spreads" and groups["86465A"] == "Spreads" and groups["06765W"] == "Spreads"
    source = out.set_index("contract_code")["source"]
    assert source["067651"].startswith("CFTC petroleum")
    assert source["06765W"].startswith("Oil-name match")
    # the query looks back over a window and includes the sweep + exclusions
    where = served["params"]["$where"]
    assert ">= '2026-08-04" in where, where
    assert "PETROLEUM AND PRODUCTS" in where and "CRACK" in where and "NOT IN" in where
    print("fetch_contracts: ok —", len(out), "contracts, window + sweep + dedupe")


def test_petroleum_where_fallback() -> None:
    cftc.list_columns = lambda dataset_id: [  # type: ignore[assignment]
        c for c in DISAGGREGATED_COLUMNS if c != "commodity_subgroup_name"
    ]
    columns = cftc.resolve_columns("72hh-3qpy", "disaggregated")
    clause = cftc._petroleum_where(columns)
    assert "like" in clause and "CRUDE" in clause
    print("petroleum filter fallback: ok")


if __name__ == "__main__":
    test_resolve_columns()
    test_tidy_shape()
    test_pretty_names()
    test_disambiguate_only_when_names_collide()
    test_group_classification()
    test_fetch_contracts_window_dedupe_and_source()
    test_petroleum_where_fallback()
    print("\nall offline parsing tests passed")
