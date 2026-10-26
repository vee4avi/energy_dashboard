"""Tests for the long / short / net tables, source tagging and the ICE suffix rule.

Run with:  python tests/test_tables.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.cftc.analytics import cot  # noqa: E402
from shared import tables  # noqa: E402


def _snapshot() -> pd.DataFrame:
    rows = []
    for product, oi, legs in [
        ("Big", 1000, {"m_money": (300, 100), "swap": (50, 150)}),
        ("Small", 100, {"m_money": (10, 30), "swap": (5, 5)}),
    ]:
        for category, (long_, short_) in legs.items():
            rows.append(
                dict(product=product, category=category, open_interest=oi, long=long_, short=short_,
                     net=long_ - short_, long_pct_oi=long_ / oi * 100,
                     short_pct_oi=short_ / oi * 100, net_pct_oi=(long_ - short_) / oi * 100)
            )
    return pd.DataFrame(rows)


def test_long_short_net_shape_order_and_labels() -> None:
    frame = cot.long_short_net(
        _snapshot(), ["swap", "m_money"], labels={"m_money": "Managed money", "swap": "Swap dealers"}
    )
    # categories follow the order requested; measures are Long, Short, Net
    assert list(frame.columns) == [
        ("Swap dealers", "Long"), ("Swap dealers", "Short"), ("Swap dealers", "Net"),
        ("Managed money", "Long"), ("Managed money", "Short"), ("Managed money", "Net"),
    ]
    # largest open interest first
    assert list(frame.index) == ["Big", "Small"]
    assert frame.loc["Big", ("Managed money", "Net")] == 200
    assert frame.loc["Small", ("Managed money", "Short")] == 30
    # asking for a category that has no data drops it quietly
    assert len(cot.long_short_net(_snapshot(), ["m_money", "nonrept"]).columns) == 3
    assert cot.long_short_net(pd.DataFrame(), ["m_money"]).empty
    print("long_short_net: ok")


def test_long_short_net_percent_units() -> None:
    frame = cot.long_short_net(_snapshot(), ["m_money"], pct=True, labels={"m_money": "MM"})
    assert abs(frame.loc["Big", ("MM", "Net")] - 20.0) < 1e-9
    assert abs(frame.loc["Small", ("MM", "Long")] - 10.0) < 1e-9
    print("percent units: ok")


def test_html_structure_and_signs() -> None:
    frame = cot.long_short_net(_snapshot(), ["m_money", "swap"], labels={"m_money": "MM", "swap": "SD"})
    markup = tables.lsn_html(frame, "Contracts", tables.limits_for(frame))
    assert "\n" not in markup, "must be one line so Markdown leaves it alone"
    assert markup.count('colspan="3"') == 2
    body = markup.split("<tbody>")[1]
    assert "+200<" in body, "positive net gets a plus"
    assert "-100<" in body, "negative net keeps its minus"
    assert ">300<" in body and "+300<" not in body, "long is never signed by default"
    # change tables sign everything
    signed = tables.lsn_html(frame, "Contracts", tables.limits_for(frame), tables.ALL_SIGNED)
    assert "+300<" in signed
    print("html structure and signs: ok")


def test_html_escapes_names_and_handles_gaps() -> None:
    cols = pd.MultiIndex.from_product([["A & B"], ["Long", "Short", "Net"]])
    frame = pd.DataFrame([[1.0, np.nan, 0.0]], columns=cols, index=["<script>x</script>"])
    markup = tables.lsn_html(frame, "Contracts", tables.limits_for(frame))
    assert "<script>" not in markup and "&lt;script&gt;" in markup
    assert "A &amp; B" in markup
    assert "na" in markup and "—" in markup
    assert ">0<" in markup, "zero prints as plain 0"
    print("escaping and gaps: ok")


def test_shared_scale_across_tables() -> None:
    cols = pd.MultiIndex.from_product([["MM"], ["Long", "Short", "Net"]])
    now = pd.DataFrame([[900.0, 100.0, 800.0]], columns=cols, index=["P"])
    before = pd.DataFrame([[400.0, 100.0, 300.0]], columns=cols, index=["P"])
    shared = tables.limits_for(now, before)
    assert shared["Long"] == 900.0 and shared["Net"] == 800.0
    # long and short share one scale; net has its own
    assert shared["Long"] == shared["Short"] and shared["Net"] != shared["Long"]
    print("shared scale: ok")


def test_ice_tagging_is_by_source_not_exchange() -> None:
    from modules.cftc import services

    catalog = pd.DataFrame(
        {
            "contract_code": ["ICE-B", "ICE-G", "02265A", "067651"],
            "product": ["Brent", "Gasoil (ICE)", "Gasoil", "WTI-Physical"],
            "exchange": ["IFEU", "IFEU", "ICEU", "NYME"],
        }
    )
    tagged = services._tag_source(catalog)
    by_code = tagged.set_index("contract_code")
    assert by_code.loc["ICE-B", "product"] == "Brent (ICE)"
    assert by_code.loc["ICE-G", "product"] == "Gasoil (ICE)", "suffix is never added twice"
    # a contract the CFTC reports on an ICE venue is still CFTC data: plain name
    assert by_code.loc["02265A", "product"] == "Gasoil"
    assert by_code.loc["02265A", "data_source"] == "CFTC"
    assert by_code.loc["067651", "product"] == "WTI-Physical"
    assert services._tag_source(tagged).equals(tagged), "idempotent"
    print("ICE tagging: ok")


if __name__ == "__main__":
    test_long_short_net_shape_order_and_labels()
    test_long_short_net_percent_units()
    test_html_structure_and_signs()
    test_html_escapes_names_and_handles_gaps()
    test_shared_scale_across_tables()
    test_ice_tagging_is_by_source_not_exchange()
    print("\nall table tests passed")
