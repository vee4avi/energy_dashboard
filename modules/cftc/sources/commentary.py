"""Weekly commentary saved by the Telegram bot.

The bot writes one JSON file per report date (``commentary/2026-09-29.json``).
Copy those files into the dashboard's own ``commentary`` folder; this module only
reads that folder. No Streamlit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_DATED = re.compile(r"\d{4}-\d{2}-\d{2}\.json")  # the bot names each file by report date


@dataclass(frozen=True)
class Commentary:
    report_date: pd.Timestamp
    prior_date: pd.Timestamp  # the week the bot compared against
    text: str
    news: str = ""
    basis: str = "combined"
    report: str = "disaggregated"
    generated_at: str = ""
    model: str = ""
    products: tuple[str, ...] = ()
    origin: str = "bot"  # "bot" or "demo"


def _parse_text(raw_text: str) -> Commentary | None:
    try:
        raw = json.loads(raw_text)
        text = str(raw["commentary"]).strip()
        if not text:
            return None
        return Commentary(
            report_date=pd.Timestamp(raw["report_date"]).normalize(),
            prior_date=pd.Timestamp(raw["prior_date"]).normalize(),
            text=text,
            news=str(raw.get("news") or "").strip(),
            basis=str(raw.get("basis") or "combined"),
            report=str(raw.get("report") or "disaggregated"),
            generated_at=str(raw.get("generated_at") or ""),
            model=str(raw.get("model") or ""),
            products=tuple((raw.get("contracts") or {}).keys()),
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return None  # a half-written or foreign file must never break the page


# --------------------------------------------------------------------------
# Folder
# --------------------------------------------------------------------------
def load_folder(folder: Path, max_files: int = 104) -> dict[pd.Timestamp, Commentary]:
    """Every readable record in ``folder`` (newest ``max_files`` only).

    A missing or empty folder is not an error: it returns {}. A file that cannot
    be read or does not look like the bot's output is skipped.
    """
    if not folder.is_dir():
        return {}
    files = sorted(
        (path for path in folder.glob("*.json") if _DATED.fullmatch(path.name)),
        key=lambda path: path.name,
        reverse=True,
    )[:max_files]
    records: dict[pd.Timestamp, Commentary] = {}
    for path in files:  # file names are ISO dates, so this is newest first
        try:
            record = _parse_text(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if record is not None:
            records.setdefault(record.report_date, record)
    return records


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------
def match(
    records: dict[pd.Timestamp, Commentary],
    report_date,
    baseline_date,
    report: str = "disaggregated",
) -> Commentary | None:
    """The record for this exact pair of dates, or None.

    The bot's numbers are week-on-week, so a record only describes the pair
    (report date, the report one week earlier). Any other baseline is a
    different comparison and gets no commentary.
    """
    if baseline_date is None or report_date is None:
        return None
    record = records.get(pd.Timestamp(report_date).normalize())
    if record is None or record.report != report:
        return None
    if record.prior_date != pd.Timestamp(baseline_date).normalize():
        return None
    return record


def for_date(
    records: dict[pd.Timestamp, Commentary], report_date, report: str = "disaggregated"
) -> Commentary | None:
    """Whatever record exists for this report date, whatever it compares against."""
    record = records.get(pd.Timestamp(report_date).normalize())
    return record if record is not None and record.report == report else None
