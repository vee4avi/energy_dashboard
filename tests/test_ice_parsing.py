"""Tests for the ICE Futures Europe COT parser.

The fixtures below are the real text of two published ICE reports
(ICE Brent futures-only, 02/07/2019, and ICE Brent futures+options, 07/07/2020),
so the parser is pinned against the actual layout rather than a guess.

Run with:  python tests/test_ice_parsing.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.cftc.sources import ice  # noqa: E402

BRENT_FUTURES_ONLY = """
Commitments of Traders Futures only B
ICE Brent Crude Futures - ICE Futures Europe
02/07/2019
MktDate OI Long Short Long Short Spreading Long Short Spreading Long Short Spreading Long Short
02/07/2019 2345720 667497 1252739 525775 58591 149237 331336 77528 266032 68593 219544 287236 50014 34813
25/06/2019 2391962 717653 1287217 526308 64541 144204 340307 74526 245218 59145 227788 311027 48100 37441
18/06/2019 2359544 703727 1258681 507230 53649 156980 352708 71840 228657 56756 242846 303309 50177 43582
11/06/2019 2378104 736727 1294555 511171 50413 157179 360283 65056 227280 53101 257761 282568 49795 43292
04/06/2019 2320580 697488 1248463 497805 53630 162870 365695 60675 219448 49458 258744 274338 53478 42412
Percent of Open Interest Represented by Each Category of Trader
MktDate
02/07/2019 100.0% 28.5% 53.4% 22.4% 2.5% 6.4% 14.1% 3.3% 11.3% 2.9% 9.4% 12.2% 2.1% 1.5%
25/06/2019 100.0% 30.0% 53.8% 22.0% 2.7% 6.0% 14.2% 3.1% 10.3% 2.5% 9.5% 13.0% 2.0% 1.6%
Number of Traders in Each Category
MktDate
02/07/2019 433 118 130 53 14 52 86 30 76 39 34 65
25/06/2019 433 122 138 46 17 50 83 33 78 36 37 69
Long Short Long Short Long Short Long Short
13.7% 19.8% 22.3% 30.8% 12.0% 13.9% 18.7% 19.8%
Percent of Open Interest Held by the Indicated Number of the Largest Traders
"""

BRENT_COMBINED = """
Commitments of Traders Futures and options B
ICE Brent Crude Futures and Options - ICE Futures Europe
07/07/2020
MktDate OI Long Short Long Short Spreading Long Short Spreading Long Short Spreading Long Short
07/07/2020 3331244 1149211 1478408 449699 97969 544613 254623 55367 361093 82978 316668 432224 56804 44903
30/06/2020 3419502 1217663 1564115 449546 98560 542208 264938 50797 369845 86945 321179 431065 57293 41735
Percent of Open Interest Represented by Each Category of Trader
MktDate
07/07/2020 100.0% 34.5% 44.4% 13.5% 2.9% 16.3% 7.6% 1.7% 10.8% 2.5% 9.5% 13.0% 1.7% 1.3%
Number of Traders in Each Category
MktDate
07/07/2020 429 130 150 53 20 58 64 39 80 47 37 69
"""

BRENT = ice.PRODUCTS["ICE-B"]


def test_parses_only_position_rows() -> None:
    frame = ice.parse_text(BRENT_FUTURES_ONLY, BRENT)
    dates = sorted({d.date().isoformat() for d in frame["report_date"]})
    assert dates == ["2019-06-04", "2019-06-11", "2019-06-18", "2019-06-25", "2019-07-02"], dates
    # five weeks × (five reported categories + the derived total)
    assert len(frame) == 5 * 6, len(frame)
    print("row selection: ok —", len(frame), "rows from 5 weeks")


def test_legs_match_the_published_percentages() -> None:
    """Cross-check the mapping against ICE's own % of open interest table."""
    frame = ice.parse_text(BRENT_FUTURES_ONLY, BRENT)
    latest = frame[frame["report_date"].eq(frame["report_date"].max())].set_index("category")
    open_interest = latest["open_interest"].iloc[0]
    assert open_interest == 2_345_720

    expected = {  # from the report's percentage block, 02/07/2019
        ("prod_merc", "long"): 28.5,
        ("prod_merc", "short"): 53.4,
        ("swap", "long"): 22.4,
        ("swap", "short"): 2.5,
        ("swap", "spread"): 6.4,
        ("m_money", "long"): 14.1,
        ("m_money", "short"): 3.3,
        ("m_money", "spread"): 11.3,
        ("other_rept", "long"): 2.9,
        ("other_rept", "short"): 9.4,
        ("other_rept", "spread"): 12.2,
        ("nonrept", "long"): 2.1,
        ("nonrept", "short"): 1.5,
    }
    for (category, side), published in expected.items():
        share = float(latest.loc[category, side]) / open_interest * 100
        assert abs(share - published) < 0.06, (category, side, share, published)
    print("leg mapping: ok — all 13 legs reconcile with ICE's own percentages")


def test_derived_total_reportable() -> None:
    frame = ice.parse_text(BRENT_FUTURES_ONLY, BRENT)
    latest = frame[frame["report_date"].eq(frame["report_date"].max())].set_index("category")
    assert latest.loc["tot_rept", "long"] == 667497 + 525775 + 331336 + 68593
    assert latest.loc["tot_rept", "short"] == 1252739 + 58591 + 77528 + 219544
    print("derived total reportable: ok")


def test_combined_layout_is_identical() -> None:
    frame = ice.parse_text(BRENT_COMBINED, BRENT)
    latest = frame[frame["report_date"].eq(frame["report_date"].max())].set_index("category")
    assert latest["open_interest"].iloc[0] == 3_331_244
    assert latest.loc["m_money", "long"] == 254623
    assert latest.loc["m_money", "short"] == 55367
    print("futures+options layout: ok")


def test_file_naming() -> None:
    import datetime as dt

    assert ice.file_stem(BRENT, "futures_only", dt.date(2019, 7, 2)) == "BrentFut_02072019"
    assert ice.file_stem(BRENT, "combined", dt.date(2020, 7, 7)) == "BrentFutOpt_07072020"
    print("file naming: ok")


def test_pdf_round_trip() -> None:
    """Optional: build a PDF in ICE's layout and read it back the way the app does."""
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.pdfgen import canvas
    except ImportError:
        print("pdf round-trip: skipped (reportlab not installed)")
        return

    import tempfile

    path = Path(tempfile.gettempdir()) / "ice_layout_fixture.pdf"
    page = canvas.Canvas(str(path), pagesize=landscape(A4))
    page.setFont("Helvetica", 7)
    y = 560
    for line in BRENT_FUTURES_ONLY.strip().splitlines():
        page.drawString(20, y, line)
        y -= 11
    page.save()

    frame = ice.parse_text(ice._extract_pdf_text(path.read_bytes()), BRENT)
    latest = frame[frame["report_date"].eq(frame["report_date"].max())].set_index("category")
    assert len(frame) == 30
    assert latest.loc["m_money", "long"] == 331336
    print("pdf round-trip: ok")


# --------------------------------------------------------------------------
# ICE's yearly history file (ice_data/COTHist*.csv)
# --------------------------------------------------------------------------
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_history_csv() -> None:
    import pandas as pd

    raw = pd.read_csv(FIXTURES / "ice_cothist_sample.csv", encoding="utf-8-sig", low_memory=False)
    fut = ice.parse_history_csv(raw, "futures_only")
    both = ice.parse_history_csv(raw, "combined")
    assert set(fut["product"]) == {"Brent (ICE)", "Gasoil (ICE)", "Dubai 1st Line (ICE)"}
    assert set(both["product"]) == {"Brent (ICE)", "Gasoil (ICE)"}, "Dubai is futures only"

    def cell(frame, product, date, category, side):
        row = frame[frame["product"].eq(product) & frame["report_date"].eq(pd.Timestamp(date))
                    & frame["category"].eq(category)]
        return int(row[side].iloc[0])

    # Figures as shown in the dashboard for 20 Oct 2026 (futures only), read from ICE's PDF.
    assert cell(fut, "Brent (ICE)", "2026-10-20", "m_money", "long") == 328_285
    assert cell(fut, "Brent (ICE)", "2026-10-20", "m_money", "short") == 106_941
    assert cell(fut, "Brent (ICE)", "2026-10-20", "prod_merc", "short") == 1_285_794
    assert cell(fut, "Gasoil (ICE)", "2026-10-20", "swap", "long") == 253_569
    assert cell(both, "Brent (ICE)", "2026-10-20", "m_money", "long") == 346_663
    assert cell(fut, "Brent (ICE)", "2026-10-13", "m_money", "long") == 314_487, "the week that was missing"

    # Every reportable leg plus non-reportable adds up to open interest, on both sides.
    for frame in (fut, both):
        legs = frame[frame["category"].ne("tot_rept")].fillna({"spread": 0})
        sums = legs.groupby(["report_date", "product"]).apply(
            lambda g: (g["long"].sum() + g["spread"].sum(), g["short"].sum() + g["spread"].sum(),
                       g["open_interest"].iloc[0])
        )
        assert all(lng == oi and sht == oi for lng, sht, oi in sums), "legs must add up to OI"
    print("history csv: ok")


def test_local_files_come_first_and_gaps_are_fetched() -> None:
    import datetime as dt

    import pandas as pd

    saved = (ice.LOCAL_DIR, ice.latest_available, ice.fetch_report, ice.fetch_year)
    fetched: list[dt.date] = []

    def fake_fetch(product, basis, date, use_cache=True):
        fetched.append(date)
        weeks = [pd.Timestamp(date) - pd.Timedelta(weeks=k) for k in range(5)]
        rows = []
        for week in weeks:
            for category, sides in ice.LEG_ORDER:
                rows.append({"report_date": week, "contract_code": product.code, "market_name": product.market_name,
                             "contract_name": product.product, "exchange": ice.EXCHANGE, "product": product.product,
                             "category": category, "open_interest": 1, "long": 1, "short": 1, "spread": pd.NA})
        return pd.DataFrame(rows)

    try:
        ice.LOCAL_DIR = FIXTURES
        ice.fetch_year = lambda year, use_cache=True: pd.DataFrame()  # no yearly download
        ice.latest_available = lambda product, basis, today=None: dt.date(2026, 10, 27)
        ice.fetch_report = fake_fetch
        history = ice.load_history(["ICE-B", "ICE-D"], "futures_only", dt.date(2026, 9, 1))
        brent = history[history["product"].eq("Brent (ICE)") & history["category"].eq("m_money")]
        dates = set(brent["report_date"].dt.date)
        assert dt.date(2026, 10, 27) in dates, "a newer week comes from the PDF"
        assert int(brent[brent["report_date"].eq("2026-10-20")]["long"].iloc[0]) == 328_285, "local file wins"
        expected = {dt.date(2026, 9, 1) + dt.timedelta(weeks=k) for k in range(9)}
        assert expected <= dates, "every Tuesday from the start date is filled"
        assert fetched[0] == dt.date(2026, 10, 27) and len(fetched) <= 3, fetched
        assert not history[history["product"].eq("Dubai 1st Line (ICE)")].empty, "Dubai comes from the file alone"
    finally:
        ice.LOCAL_DIR, ice.latest_available, ice.fetch_report, ice.fetch_year = saved
    print("local first, gaps fetched: ok")


def test_yearly_download_fills_history_before_pdfs() -> None:
    import datetime as dt
    import tempfile


    sample = (FIXTURES / "ice_cothist_sample.csv").read_bytes()
    requested: list[str] = []

    class Reply:
        def __init__(self, code, content=b""):
            self.status_code, self.content = code, content

    class Session:
        def get(self, url, timeout=None):
            requested.append(url)
            return Reply(200, sample) if url.endswith("COTHist2026.csv") else Reply(404)

    saved = (ice.LOCAL_DIR, ice.CACHE_DIR, ice._SESSION, ice.latest_available)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ice.LOCAL_DIR = Path(tmp) / "none"
            ice.CACHE_DIR = Path(tmp) / "cache"
            ice._SESSION = Session()
            ice.latest_available = lambda *a, **k: None  # no PDFs needed
            history = ice.load_history(["ICE-B"], "combined", dt.date(2025, 6, 1))
            assert "https://www.ice.com/publicdocs/futures/COTHist2026.csv" in requested
            assert "https://www.ice.com/publicdocs/futures/COTHist2025.csv" in requested
            mm = history[history["category"].eq("m_money")]
            assert int(mm[mm["report_date"].eq("2026-10-20")]["long"].iloc[0]) == 346_663
            assert (Path(tmp) / "cache" / "COTHist2026.csv").exists(), "the download is kept"

            requested.clear()  # within the refresh window nothing is downloaded again
            ice.fetch_year(2026)
            assert requested == []
            catalog = ice.catalog("combined")
            assert set(catalog["product"]) == {"Brent (ICE)", "Gasoil (ICE)"}
    finally:
        ice.LOCAL_DIR, ice.CACHE_DIR, ice._SESSION, ice.latest_available = saved
    print("yearly download: ok")


if __name__ == "__main__":
    test_history_csv()
    test_local_files_come_first_and_gaps_are_fetched()
    test_yearly_download_fills_history_before_pdfs()
    test_parses_only_position_rows()
    test_legs_match_the_published_percentages()
    test_derived_total_reportable()
    test_combined_layout_is_identical()
    test_file_naming()
    test_pdf_round_trip()
    print("\nall ICE parsing tests passed")
