"""ICE Futures Europe Commitments of Traders.

Three sources, in this order:

1. The ``ice_data`` folder next to app.py: ICE's yearly history files, put there by hand.
2. ICE's yearly history files, downloaded (one per year, every market, both bases):

       https://www.ice.com/publicdocs/futures/COTHist2026.csv

3. ICE's weekly PDFs, only for weeks the first two don't have:

       https://www.ice.com/publicdocs/cot_report/automated/BrentFut_16092026.pdf
       https://www.ice.com/publicdocs/cot_report/BrentFutOpt_24042018.pdf   (older path)

   The date in a PDF's name is the **Tuesday** the positions were taken, and each file
   carries five weeks. Layout (identical for futures-only and futures+options),
   fourteen numbers per row:

       MktDate | OI | P/M long short | Swap long short spread
               | Managed money long short spread | Other rept long short spread
               | Non-reportable long short

ICE follows the CFTC's disaggregated definitions, so the output slots straight
into the same tidy frame as ``sources.cftc``. Downloads are cached on disk.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

BASE_PATHS = (
    "https://www.ice.com/publicdocs/cot_report/automated/",
    "https://www.ice.com/publicdocs/cot_report/",
)

CACHE_DIR = Path(os.getenv("COT_CACHE_DIR", ".cache")) / "ice"
# Bump when the loading logic changes, so the dashboard's cached ICE results are thrown
# away instead of being served until they expire.
VERSION = "2026-10-29-robust-parse"
REQUEST_TIMEOUT = 45
WEEKS_PER_FILE = 5
FIRST_REPORT = dt.date(2011, 6, 7)  # ICE's first published COT


class IceDataError(RuntimeError):
    """Raised when an ICE report cannot be fetched or parsed."""


@dataclass(frozen=True)
class IceProduct:
    code: str  # pseudo contract code used across the app
    slug: str  # the file-name stem ICE uses for its weekly PDFs ("" = no PDF, local files only)
    product: str  # display name
    market_name: str


# ICE publishes these two for petroleum. To add another contract, find its file
# stem in the ICE report centre URL and add an entry here — nothing else changes.
PRODUCTS: dict[str, IceProduct] = {
    "ICE-B": IceProduct(
        code="ICE-B",
        slug="Brent",
        product="Brent (ICE)",
        market_name="ICE BRENT CRUDE FUTURES - ICE FUTURES EUROPE",
    ),
    "ICE-G": IceProduct(
        code="ICE-G",
        slug="Gasoil",
        product="Gasoil (ICE)",
        market_name="ICE GASOIL FUTURES - ICE FUTURES EUROPE",
    ),
    # Only in ICE's yearly history file (futures only); there is no weekly PDF for it.
    "ICE-D": IceProduct(
        code="ICE-D",
        slug="",
        product="Dubai 1st Line (ICE)",
        market_name="ICE DUBAI 1ST LINE FUTURES - ICE FUTURES EUROPE",
    ),
}

EXCHANGE = "IFEU"

# Column order inside each data row, after MktDate and open interest.
LEG_ORDER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("prod_merc", ("long", "short")),
    ("swap", ("long", "short", "spread")),
    ("m_money", ("long", "short", "spread")),
    ("other_rept", ("long", "short", "spread")),
    ("nonrept", ("long", "short")),
)
EXPECTED_VALUES = 1 + sum(len(legs) for _, legs in LEG_ORDER)  # 14

_ROW = re.compile(r"^(\d{2}/\d{2}/\d{4})((?:\s+-?[\d,]+){%d})\s*$" % EXPECTED_VALUES)

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = "petroleum-cot-dashboard/0.1"


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
def parse_text(text: str, product: IceProduct) -> pd.DataFrame:
    """Turn the extracted PDF text into a tidy frame.

    Only the position block matches: the percentage block carries ``%`` signs
    and the trader-count block has twelve numbers rather than fourteen.
    """
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if "%" in line:
            continue
        match = _ROW.match(line)
        if not match:
            continue
        date = dt.datetime.strptime(match.group(1), "%d/%m/%Y").date()
        values = [int(v.replace(",", "")) for v in match.group(2).split()]
        open_interest, legs = values[0], values[1:]

        cursor = 0
        for category, sides in LEG_ORDER:
            record = {
                "report_date": pd.Timestamp(date),
                "contract_code": product.code,
                "market_name": product.market_name,
                "contract_name": product.product,
                "exchange": EXCHANGE,
                "product": product.product,
                "category": category,
                "open_interest": open_interest,
                "long": 0,
                "short": 0,
                "spread": pd.NA,
            }
            for side in sides:
                record[side] = legs[cursor]
                cursor += 1
            records.append(record)

    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame(records)
    return pd.concat([frame, _total_reportable(frame)], ignore_index=True)


def _total_reportable(frame: pd.DataFrame) -> pd.DataFrame:
    """ICE does not print a reportable total — derive it like the CFTC's."""
    reportable = frame[frame["category"].isin({"prod_merc", "swap", "m_money", "other_rept"})]
    if reportable.empty:
        return pd.DataFrame()
    totals = (
        reportable.groupby(["report_date", "contract_code"], as_index=False)
        .agg(long=("long", "sum"), short=("short", "sum"), spread=("spread", "sum"))
    )
    meta = frame.drop_duplicates(["report_date", "contract_code"])[
        ["report_date", "contract_code", "market_name", "contract_name", "exchange",
         "product", "open_interest"]
    ]
    totals = totals.merge(meta, on=["report_date", "contract_code"], how="left")
    totals["category"] = "tot_rept"
    return totals


# --------------------------------------------------------------------------
# ICE's yearly history file (COTHist2026.csv and so on)
# --------------------------------------------------------------------------
# Put the files in the ice_data folder next to app.py. They use the CFTC's
# disaggregated column names, one row per market and week, with both futures-only
# and futures+options rows; anything else in them (other markets) is ignored.
LOCAL_DIR = Path(__file__).resolve().parents[3] / "ice_data"
HIST_COMMODITY = {"B": "ICE-B", "G": "ICE-G", "Dubai_1st": "ICE-D"}
HIST_BASIS = {"FutOnly": "futures_only", "Combined": "combined"}
HIST_PREFIX = {
    "prod_merc": "Prod_Merc_Positions",
    "swap": "Swap_Positions",
    "m_money": "M_Money_Positions",
    "other_rept": "Other_Rept_Positions",
    "nonrept": "NonRept_Positions",
}


# Market names (start of) for each commodity code: the full file can hold more than one
# market under a code, and only the outright futures (and futures+options) are wanted.
HIST_MARKETS = {
    "B": "ICE BRENT CRUDE FUTURES",
    "G": "ICE GASOIL FUTURES",
    "Dubai_1st": "ICE DUBAI 1ST LINE",
}


def _number(value):
    """A count from the file: "1,234", 1234, 1234.0 or blank (-> NA)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return pd.NA
    text = str(value).replace(",", "").strip()
    if not text or text.lower() == "nan":
        return pd.NA
    return int(round(float(text)))


def _hist_date(value) -> pd.Timestamp:
    """The YYMMDD column, which may come back as text, an integer or a float."""
    digits = str(int(float(str(value).strip()))).zfill(6)
    return pd.Timestamp(dt.datetime.strptime(digits, "%y%m%d"))


def parse_history_csv(raw: pd.DataFrame, basis: str) -> pd.DataFrame:
    """One ICE history file -> the same tidy frame as parse_text, for one basis.

    Rows that can't be read are skipped, so one odd market never hides the rest.
    """
    if raw is None or raw.empty:
        return pd.DataFrame()
    raw = raw.rename(columns=lambda c: str(c).lstrip("\ufeff").strip())
    needed = {"As_of_Date_In_Form_YYMMDD", "CFTC_Commodity_Code", "FutOnly_or_Combined",
              "Open_Interest_All", "Market_and_Exchange_Names"}
    if not needed <= set(raw.columns):
        return pd.DataFrame()
    code = raw["CFTC_Commodity_Code"].astype(str).str.strip()
    name = raw["Market_and_Exchange_Names"].astype(str).str.strip().str.upper()
    wanted = code.map(HIST_MARKETS)
    keep = (
        raw["FutOnly_or_Combined"].astype(str).str.strip().map(HIST_BASIS).eq(basis)
        & wanted.notna()
        & pd.Series([n.startswith(w) if isinstance(w, str) else False for n, w in zip(name, wanted)],
                    index=raw.index)
    )

    records: list[dict] = []
    for _, row in raw[keep].iterrows():
        try:
            product = PRODUCTS[HIST_COMMODITY[str(row["CFTC_Commodity_Code"]).strip()]]
            date = _hist_date(row["As_of_Date_In_Form_YYMMDD"])
            legs = []
            for category, sides in LEG_ORDER:
                record = {
                    "report_date": date,
                    "contract_code": product.code,
                    "market_name": product.market_name,
                    "contract_name": product.product,
                    "exchange": EXCHANGE,
                    "product": product.product,
                    "category": category,
                    "open_interest": _number(row["Open_Interest_All"]),
                    "long": 0,
                    "short": 0,
                    "spread": pd.NA,
                }
                for side in sides:
                    record[side] = _number(row.get(f"{HIST_PREFIX[category]}_{side.title()}_All"))
                legs.append(record)
        except (ValueError, TypeError, KeyError):
            continue
        records.extend(legs)
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records)
    for column in ("open_interest", "long", "short"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype("int64")
    frame["spread"] = pd.to_numeric(frame["spread"], errors="coerce")
    return pd.concat([frame, _total_reportable(frame)], ignore_index=True)


HIST_URL = "https://www.ice.com/publicdocs/futures/COTHist{year}.csv"
HIST_FIRST_YEAR = FIRST_REPORT.year
HIST_REFRESH_HOURS = 6  # how long a downloaded current-year file is trusted


def fetch_year(year: int, use_cache: bool = True) -> pd.DataFrame:
    """ICE's history file for one year, as a raw table ({} if it can't be had).

    Past years never change, so once downloaded they are kept. The current year is
    downloaded again after HIST_REFRESH_HOURS so new weeks appear.
    """
    cached = CACHE_DIR / f"COTHist{year}.csv"
    fresh = cached.exists() and (
        year < dt.date.today().year
        or dt.datetime.now().timestamp() - cached.stat().st_mtime < HIST_REFRESH_HOURS * 3600
    )
    if not (use_cache and fresh):
        try:
            response = _SESSION.get(HIST_URL.format(year=year), timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            response = None
        if response is not None and response.status_code == 200 and b"As_of_Date" in response.content[:4000]:
            if use_cache:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(response.content)
            else:
                return pd.read_csv(io.BytesIO(response.content), encoding="utf-8-sig", low_memory=False)
    if cached.exists():  # a stale copy beats nothing when ICE can't be reached
        try:
            return pd.read_csv(cached, encoding="utf-8-sig", low_memory=False)
        except (OSError, ValueError):
            return pd.DataFrame()
    return pd.DataFrame()


def load_downloaded(basis: str, start: dt.date) -> pd.DataFrame:
    """Every year from ``start`` to today, from ICE's yearly history files."""
    frames = []
    for year in range(max(start.year, HIST_FIRST_YEAR), dt.date.today().year + 1):
        parsed = parse_history_csv(fetch_year(year), basis)
        if not parsed.empty:
            frames.append(parsed)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_local(basis: str, folder: Path | None = None) -> pd.DataFrame:
    """Every week in the ice_data folder for one basis ({} if the folder is empty)."""
    folder = folder or LOCAL_DIR
    frames = []
    for path in sorted(folder.glob("*.csv")) if folder.is_dir() else []:
        try:
            raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        except (OSError, ValueError):
            continue
        parsed = parse_history_csv(raw, basis)
        if not parsed.empty:
            frames.append(parsed)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # A later file wins if two files hold the same week.
    return out.drop_duplicates(["report_date", "contract_code", "category"], keep="last")


def _extract_pdf_text(payload: bytes) -> str:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise IceDataError(
            "Reading ICE reports needs pdfplumber — run: pip install pdfplumber"
        ) from exc

    import io

    with pdfplumber.open(io.BytesIO(payload)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def file_stem(product: IceProduct, basis: str, date: dt.date) -> str:
    suffix = "Fut" if basis == "futures_only" else "FutOpt"
    return f"{product.slug}{suffix}_{date:%d%m%Y}"


def _cache_path(stem: str) -> Path:
    return CACHE_DIR / f"{stem}.csv"


def fetch_report(
    product: IceProduct, basis: str, date: dt.date, use_cache: bool = True
) -> pd.DataFrame:
    """One ICE report (the given Tuesday plus the four weeks before it)."""
    stem = file_stem(product, basis, date)
    cached = _cache_path(stem)
    if use_cache and cached.exists():
        frame = pd.read_csv(cached, parse_dates=["report_date"])
        return frame

    payload = None
    for base in BASE_PATHS:
        try:
            response = _SESSION.get(f"{base}{stem}.pdf", timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            continue
        if response.status_code == 200 and response.content[:4] == b"%PDF":
            payload = response.content
            break
    if payload is None:
        return pd.DataFrame()

    frame = parse_text(_extract_pdf_text(payload), product)
    if not frame.empty and use_cache:
        cached.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(cached, index=False)
    return frame


def _tuesdays(start: dt.date, end: dt.date) -> list[dt.date]:
    cursor = end - dt.timedelta(days=(end.weekday() - 1) % 7)  # back to a Tuesday
    out = []
    while cursor >= start:
        out.append(cursor)
        cursor -= dt.timedelta(weeks=1)
    return out


def latest_available(product: IceProduct, basis: str, today: dt.date | None = None) -> dt.date | None:
    """Walk back from this week until a published report answers."""
    today = today or dt.date.today()
    for candidate in _tuesdays(today - dt.timedelta(weeks=4), today):
        if not fetch_report(product, basis, candidate).empty:
            return candidate
    return None


MAX_PDF_FETCHES = 40  # per contract per load; each PDF covers five weeks


def load_history(
    product_codes: list[str], basis: str, start: dt.date | None = None
) -> pd.DataFrame:
    """Tidy history for the requested ICE contracts.

    Weeks come first from the ice_data folder, then from ICE's yearly history files
    (downloaded). Any week still missing from ``start`` to the latest published report
    is fetched from ICE's weekly PDFs as a fallback: always the newest
    missing week first, so one PDF fills up to five weeks and a failed week is tried
    again on its own rather than leaving a five-week hole.
    """
    start = max(start or FIRST_REPORT, FIRST_REPORT)
    today = dt.date.today()
    files = [frame for frame in (load_local(basis), load_downloaded(basis, start)) if not frame.empty]
    # The folder comes first, so it wins if a week appears in both.
    local = pd.concat(files, ignore_index=True) if files else pd.DataFrame()
    frames: list[pd.DataFrame] = []

    for code in product_codes:
        product = PRODUCTS.get(code)
        if product is None:
            continue
        mine = local[local["contract_code"].eq(code)] if not local.empty else pd.DataFrame()
        collected = [mine] if not mine.empty else []
        have = set(pd.to_datetime(mine["report_date"]).dt.date) if not mine.empty else set()

        anchor = latest_available(product, basis, today) if product.slug else None
        if anchor is not None:
            missing = [d for d in _tuesdays(start, anchor) if d not in have]
            for _ in range(MAX_PDF_FETCHES):
                if not missing:
                    break
                wanted = missing[0]
                report = fetch_report(product, basis, wanted)
                covered = {wanted}
                if not report.empty:
                    collected.append(report)
                    covered |= set(pd.to_datetime(report["report_date"]).dt.date)
                missing = [d for d in missing if d not in covered]

        if collected:
            frames.append(pd.concat(collected, ignore_index=True))

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out["report_date"] = pd.to_datetime(out["report_date"])
    out = out[out["report_date"].ge(pd.Timestamp(start))]
    return (
        # Local files come first in each contract's frames, so they win over a PDF.
        out.drop_duplicates(["report_date", "contract_code", "category"], keep="first")
        .sort_values(["product", "category", "report_date"])
        .reset_index(drop=True)
    )


def catalog(basis: str = "futures_only") -> pd.DataFrame:
    """One row per ICE contract, with the latest open interest (local files or ICE)."""
    files = [frame for frame in (load_local(basis), load_downloaded(basis, dt.date.today())) if not frame.empty]
    local = pd.concat(files, ignore_index=True) if files else pd.DataFrame()
    rows = []
    for product in PRODUCTS.values():
        found = []
        if not local.empty:
            found.append(local[local["contract_code"].eq(product.code)])
        if product.slug:
            anchor = latest_available(product, basis)
            if anchor is not None:
                found.append(fetch_report(product, basis, anchor))
        found = [frame for frame in found if not frame.empty]
        if not found:
            continue
        both = pd.concat(found, ignore_index=True)
        both["report_date"] = pd.to_datetime(both["report_date"])
        latest = both[both["report_date"].eq(both["report_date"].max())]
        rows.append(
            {
                "contract_code": product.code,
                "market_name": product.market_name,
                "contract_name": product.product,
                "product": product.product,
                "exchange": EXCHANGE,
                "subgroup": "PETROLEUM AND PRODUCTS",
                "source": "ICE Futures Europe report",
                "last_report": latest["report_date"].max(),
                "open_interest": float(pd.to_numeric(latest["open_interest"]).max()),
                "as_of": latest["report_date"].max().date(),
            }
        )
    return pd.DataFrame(rows)
