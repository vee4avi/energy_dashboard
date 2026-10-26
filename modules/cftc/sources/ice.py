"""ICE Futures Europe Commitments of Traders.

ICE publishes COT for ICE Brent and ICE Gasoil free of charge, but as weekly
PDFs rather than an API:

    https://www.ice.com/publicdocs/cot_report/automated/BrentFut_16092026.pdf
    https://www.ice.com/publicdocs/cot_report/BrentFutOpt_24042018.pdf   (older path)

The date in the file name is the **Tuesday** the positions were taken, and each
file carries five weeks of history — so a three-year backfill needs roughly
thirty fetches, not a hundred and fifty. Parsed files are cached on disk, so
history accumulates and later runs only fetch what is new.

Layout (identical for futures-only and futures+options), fourteen numbers per row:

    MktDate | OI | P/M long short | Swap long short spread
            | Managed money long short spread | Other rept long short spread
            | Non-reportable long short

ICE follows the CFTC's disaggregated definitions, so the output slots straight
into the same tidy frame as ``sources.cftc``.
"""

from __future__ import annotations

import datetime as dt
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
REQUEST_TIMEOUT = 45
WEEKS_PER_FILE = 5
MAX_GAP_FETCHES = 8
FIRST_REPORT = dt.date(2011, 6, 7)  # ICE's first published COT


class IceDataError(RuntimeError):
    """Raised when an ICE report cannot be fetched or parsed."""


@dataclass(frozen=True)
class IceProduct:
    code: str  # pseudo contract code used across the app
    slug: str  # the file-name stem ICE uses
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


def load_history(
    product_codes: list[str], basis: str, start: dt.date | None = None
) -> pd.DataFrame:
    """Tidy history for the requested ICE contracts."""
    start = max(start or FIRST_REPORT, FIRST_REPORT)
    today = dt.date.today()
    frames: list[pd.DataFrame] = []

    for code in product_codes:
        product = PRODUCTS.get(code)
        if product is None:
            continue

        anchor = latest_available(product, basis, today)
        if anchor is None:
            continue

        collected: list[pd.DataFrame] = []
        cursor = anchor
        while cursor >= start:
            report = fetch_report(product, basis, cursor)
            if not report.empty:
                collected.append(report)
            cursor -= dt.timedelta(weeks=WEEKS_PER_FILE)

        if not collected:
            continue
        history = pd.concat(collected, ignore_index=True)

        # A skipped publication (holidays) leaves a hole; fill a few directly.
        have = set(pd.to_datetime(history["report_date"]).dt.date)
        missing = [d for d in _tuesdays(start, anchor) if d not in have][:MAX_GAP_FETCHES]
        for date in missing:
            patch = fetch_report(product, basis, date)
            if not patch.empty:
                history = pd.concat([history, patch], ignore_index=True)

        frames.append(history)

    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True)
    out["report_date"] = pd.to_datetime(out["report_date"])
    out = out[out["report_date"].ge(pd.Timestamp(start))]
    return (
        out.drop_duplicates(["report_date", "contract_code", "category"])
        .sort_values(["product", "category", "report_date"])
        .reset_index(drop=True)
    )


def catalog(basis: str = "futures_only") -> pd.DataFrame:
    """One row per ICE contract, with the latest open interest."""
    rows = []
    for product in PRODUCTS.values():
        anchor = latest_available(product, basis)
        if anchor is None:
            continue
        report = fetch_report(product, basis, anchor)
        if report.empty:
            continue
        latest = report[report["report_date"].eq(report["report_date"].max())]
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
                "open_interest": float(latest["open_interest"].max()),
                "as_of": latest["report_date"].max().date(),
            }
        )
    return pd.DataFrame(rows)
