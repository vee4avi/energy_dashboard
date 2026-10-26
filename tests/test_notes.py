"""Tests for the commentary cards, the fixed-width tables and the Compare breakdown.

Run with:  python tests/test_notes.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd

os.environ.setdefault("COT_DEMO", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared import notes, tables  # noqa: E402

HEADINGS = """# CFTC COT Analysis — Petroleum Complex | Week of October 6, 2026

---

## 🔑 Key Positioning Shifts
Net longs fell to $104 from $135. **WTI** led.
Second line.

## ⚖️ Physical vs Financial
Commercials hedged.

## 🌐 Macro & Fundamentals
- one
- two

## ⚡ Risk Outlook
Downside.

— End —"""

INLINE = (
    "🔑 **Key Positioning Shifts** — Managed money added.\n\n"
    "⚖️ **Physical vs Financial** — Producers hedged.\n\n"
    "🌐 **Macro** — x\n\n⚡ **Risk Outlook** — y\n\n— End —"
)


def test_parse_heading_format() -> None:
    title, intro, sections = notes.parse(HEADINGS)
    assert title.startswith("CFTC COT Analysis") and not intro
    assert [s.title for s in sections] == [
        "🔑 Key Positioning Shifts", "⚖️ Physical vs Financial",
        "🌐 Macro & Fundamentals", "⚡ Risk Outlook",
    ]
    assert "End" not in sections[-1].body and "---" not in "".join(s.body for s in sections)
    print("parse headings: ok")


def test_parse_inline_emoji_format() -> None:
    title, _, sections = notes.parse(INLINE)
    assert title == "" and [s.body for s in sections] == [
        "Managed money added.", "Producers hedged.", "x", "y",
    ]
    print("parse inline: ok")


def test_html_is_one_line_and_escapes_dollars() -> None:
    markup = notes.note_html(HEADINGS)
    assert "\n" not in markup, "a newline would let Markdown break the HTML block"
    assert markup.count('class="cot-card"') == 4
    assert "$" not in markup and "&#36;104" in markup
    assert "<strong>WTI</strong>" in markup and "<li>one</li>" in markup
    assert notes.note_html("plain text, no sections") == ""
    assert "&lt;script&gt;" in notes.note_html("## 🔑 A\n<script>")
    print("html: ok")


def test_tables_share_column_widths() -> None:
    columns = pd.MultiIndex.from_product([["Managed money", "Swap dealers"], ["Long", "Short", "Net"]])
    big = pd.DataFrame([[1_186_515.0] * 6, [2.0] * 6], columns=columns, index=["A", "B"])
    small = pd.DataFrame([[3.0] * 6, [-4.0] * 6], columns=columns, index=["A", "B"])
    limits = tables.limits_for(big, small)
    one, two = (tables.lsn_html(f, "Contracts", limits) for f in (big, small))

    def layout(markup: str) -> tuple:
        return (
            re.search(r"<colgroup>.*?</colgroup>", markup).group(0),
            re.search(r'<table class="cot-table" style="([^"]*)"', markup).group(1),
        )

    assert layout(one) == layout(two), "same columns, same widths, whatever the numbers"
    assert "max-width" not in tables.lsn_html(big, "Contracts", limits, max_width=None)
    print("table widths: ok")


def test_breakdown_frames() -> None:
    from modules.cftc.analytics import cot
    from modules.cftc.sources import demo
    from modules.cftc.ui import views

    class F:  # the few fields the helper reads
        unit = "Contracts"
        report = "disaggregated"
        categories = ["m_money", "swap"]

    frame = cot.enrich(demo.positions("disaggregated"))
    dates = cot.report_dates(frame)[:3]
    view = frame[frame["category"].isin(F.categories)]
    levels, changes = views._breakdown_frames(view, dates, F, "vs previous")
    assert len(levels) == 2
    for label, level in levels.items():
        assert level.columns.nlevels == 2
        assert [m for _, m in level.columns[:3]] == ["Long", "Short", "Net"]
        assert len(level.columns) == 3 * len(dates)
        pick = lambda m: level[[c for c in level.columns if c[1] == m]].to_numpy()  # noqa: E731
        assert ((pick("Long") - pick("Short")) == pick("Net")).all()
        assert len(changes[label].columns) == 3 * (len(dates) - 1)
    _, anchored = views._breakdown_frames(view, dates, F, "vs first")
    first = {c[0].split(" vs ")[1] for c in next(iter(anchored.values())).columns}
    assert len(first) == 1, "'vs first' anchors every change on the same date"
    print("breakdown frames: ok")


def test_history_table() -> None:
    from modules.cftc.analytics import cot
    from modules.cftc.sources import demo
    from modules.cftc.ui import views

    frame = cot.enrich(demo.positions("disaggregated"))
    view = frame[frame["product"].eq("WTI Physical Nymex")]
    labels = {"prod_merc": "Prod/Merc", "swap": "Swap", "m_money": "MM"}
    table = views.history_frame(view, ["prod_merc", "swap", "m_money"], labels, False, True)
    assert table.index.is_monotonic_decreasing, "newest week first"
    measures = [m for g, m in table.columns if g == "Prod/Merc"]
    assert measures == ["Long", "Short", "Net", "Long Δ", "Short Δ", "Net Δ"]
    assert [m for g, m in table.columns if g == "Open interest"] == ["OI", "OI Δ"]
    newest, previous = table.index[0], table.index[1]
    assert table.loc[newest, ("MM", "Net Δ")] == table.loc[newest, ("MM", "Net")] - table.loc[previous, ("MM", "Net")]
    assert table.loc[newest, ("MM", "Net")] == table.loc[newest, ("MM", "Long")] - table.loc[newest, ("MM", "Short")]
    assert views.history_frame(view, ["swap"], labels, False, False).shape[1] == 3 + 1

    markup = tables.history_html(table.head(3), pct=False)
    assert "\n" not in markup and markup.count("<tr>") == 2 + 3
    assert 'class="up' in markup and 'class="down' in markup
    assert tables._history_cell(float("nan"), "Net Δ", False) == ("", "blank")
    assert tables._history_cell(0.0, "Net Δ", False) == ("0", "flat")
    assert tables._history_cell(1234.0, "Net Δ", False) == ("+1,234", "up")
    assert tables._history_cell(-1234.0, "Net", False) == ("-1,234", "")
    assert tables._history_cell(1.26, "Net Δ", True) == ("+1.3", "up")
    assert tables._history_cell(1234567.0, "OI", True) == ("1,234,567", "")
    print("history table: ok")


def test_full_table_tab_runs() -> None:
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[1]
    at = AppTest.from_file(str(root / "tests" / "cftc_entry.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    for window in ("1 year", "All loaded"):
        at.selectbox(key="full_window").set_value(window).run()
        assert not at.exception, [e.value for e in at.exception]
    at.toggle(key="full_changes").set_value(False).run()
    assert not at.exception, [e.value for e in at.exception]
    at.multiselect(key="full_categories").set_value(["m_money", "nonrept", "tot_rept"]).run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Δ" not in " ".join(m.value for m in at.markdown if "cot-hist" in m.value)
    for product in at.selectbox(key="full_product").options:
        at.selectbox(key="full_product").set_value(product).run()
        assert not at.exception, (product, [e.value for e in at.exception])
    print("full table tab: ok")


if __name__ == "__main__":
    test_parse_heading_format()
    test_parse_inline_emoji_format()
    test_html_is_one_line_and_escapes_dollars()
    test_tables_share_column_widths()
    test_breakdown_frames()
    test_history_table()
    test_full_table_tab_runs()
    print("\nall note and layout tests passed")
