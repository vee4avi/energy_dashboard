"""Tests for saved commentary read from the commentary folder, and the Snapshot panel.

Run with:  python tests/test_commentary.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["COT_DEMO"] = "1"

import pandas as pd  # noqa: E402

from modules.cftc.sources import commentary  # noqa: E402

SAMPLE = {
    "schema": 1, "report": "disaggregated", "basis": "combined",
    "report_date": "2026-09-29", "prior_date": "2026-09-22",
    "generated_at": "2026-10-02T20:35:00+00:00", "model": "claude-sonnet-4-6",
    "commentary": "🔑 Key Positioning Shifts — Managed money bought crude.",
    "news": "OPEC+ held output.",
    "contracts": {"Brent LD (NYMEX)": {}, "WTI Fin (NYMEX)": {}},
}


def test_folder_reader() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        assert commentary.load_folder(folder / "missing") == {}, "no folder is not an error"
        assert commentary.load_folder(folder) == {}
        (folder / "2026-09-29.json").write_text(json.dumps(SAMPLE), encoding="utf-8")
        (folder / "2026-09-22.json").write_text(
            json.dumps({**SAMPLE, "report_date": "2026-09-22", "prior_date": "2026-09-15"}), encoding="utf-8")
        (folder / "2026-08-03.json").write_text("{not json", encoding="utf-8")
        (folder / "2026-08-10.json").write_text(json.dumps({**SAMPLE, "commentary": "  "}), encoding="utf-8")
        (folder / "2026-08-17.json").write_text(json.dumps({"hello": 1}), encoding="utf-8")
        (folder / "notes.json").write_text(json.dumps(SAMPLE), encoding="utf-8")  # not date-named: ignored
        (folder / "README.md").write_text("ignored", encoding="utf-8")
        records = commentary.load_folder(folder)
        assert sorted(records) == [pd.Timestamp("2026-09-22"), pd.Timestamp("2026-09-29")]
        assert list(commentary.load_folder(folder, max_files=1)) == [pd.Timestamp("2026-09-29")]
    print("folder reader: ok")


def test_match() -> None:
    record = commentary._parse_text(json.dumps(SAMPLE))
    records = {record.report_date: record}
    this_week, last_week = pd.Timestamp("2026-09-29"), pd.Timestamp("2026-09-22")
    assert record.products == ("Brent LD (NYMEX)", "WTI Fin (NYMEX)") and record.basis == "combined"
    assert commentary.match(records, this_week, last_week) is record
    assert commentary.match(records, this_week, pd.Timestamp("2026-09-01")) is None
    assert commentary.match(records, this_week, None) is None
    assert commentary.match(records, this_week, last_week, report="legacy") is None
    assert commentary.for_date(records, this_week) is record
    assert commentary.for_date(records, pd.Timestamp("2020-01-07")) is None
    print("match: ok")


def _app():
    from streamlit.testing.v1 import AppTest

    os.chdir(ROOT)
    return AppTest.from_file(str(ROOT / "tests" / "cftc_entry.py"), default_timeout=90)


def test_panel_and_no_analysis_box() -> None:
    at = _app().run()
    assert not at.exception, [e.value for e in at.exception]
    text = "\n".join(m.value for m in at.markdown)
    assert "Desk commentary" in text and "DEMO COMMENTARY" in text
    assert "Analyse these dates" not in text
    assert not [b for b in at.button if b.key == "analysis_run"]
    at.selectbox(key="snap_baseline_choice").set_value("4 weeks ago").run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Desk commentary" not in "\n".join(m.value for m in at.markdown)
    print("panel: ok")


def test_empty_folder_says_where_to_put_files() -> None:
    from modules.cftc import services

    services.DEMO_MODE = False
    services.load_commentary.clear()
    original = services.COMMENTARY_DIR
    try:
        with tempfile.TemporaryDirectory() as tmp:
            services.COMMENTARY_DIR = Path(tmp)
            assert services.load_commentary() == ({}, "")
    finally:
        services.COMMENTARY_DIR = original
        services.DEMO_MODE = True
        services.load_commentary.clear()
    print("empty folder: ok")


if __name__ == "__main__":
    test_folder_reader()
    test_match()
    test_panel_and_no_analysis_box()
    test_empty_folder_says_where_to_put_files()
    print("\nall commentary tests passed")
