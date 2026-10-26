"""Weekly commentary saved by the Telegram bot.

The bot writes one JSON file per report date (``commentary/2026-09-29.json``).
This module only reads them, straight from the GitHub repository the bot commits
to. No Streamlit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests

GITHUB_API = "https://api.github.com"
_REPO = re.compile(r"[\w.-]+/[\w.-]+")
_FOLDER = re.compile(r"[\w.\-/]*")


class FetchError(RuntimeError):
    """Reading from GitHub failed. The message is safe to show (it never holds a token)."""


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
# GitHub
# --------------------------------------------------------------------------
# Files are named by date and never change once written, so a parsed file is
# kept by its content hash: after the first load only new weeks are downloaded.
_BY_SHA: dict[str, Commentary | None] = {}


def _get(url: str, headers: dict, timeout: float, params: dict | None = None):
    try:
        return requests.get(url, headers=headers, params=params, timeout=timeout)
    except requests.RequestException as error:
        raise FetchError(f"network error ({type(error).__name__})") from error


def _check(reply) -> None:
    code = reply.status_code
    if code == 200:
        return
    if code == 401:
        raise FetchError("the token was rejected (HTTP 401)")
    if code in (403, 429):
        raise FetchError(f"access denied or rate limit reached (HTTP {code})")
    raise FetchError(f"GitHub answered HTTP {code}")


def load_github(
    repo: str,
    branch: str = "main",
    folder: str = "commentary",
    token: str | None = None,
    max_files: int = 104,
    timeout: float = 15,
) -> dict[pd.Timestamp, Commentary]:
    """Every readable record in ``folder`` of ``owner/repo``, newest ``max_files`` only.

    A repo that has no such folder yet (the bot has not run) returns {}. Anything
    else that goes wrong raises FetchError.
    """
    folder = (folder or "").strip("/")
    if not _REPO.fullmatch(repo or "") or ".." in folder or not _FOLDER.fullmatch(folder):
        raise FetchError("COMMENTARY_REPO should look like owner/repository")

    api_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    raw_headers: dict[str, str] = {}
    if token:
        api_headers["Authorization"] = f"Bearer {token}"
        raw_headers["Authorization"] = f"Bearer {token}"

    listing = _get(
        f"{GITHUB_API}/repos/{repo}/contents/{folder}", api_headers, timeout, {"ref": branch}
    )
    if listing.status_code == 404:
        return {}
    _check(listing)
    try:
        entries = listing.json()
    except ValueError as error:
        raise FetchError("GitHub sent an unreadable reply") from error
    if not isinstance(entries, list):
        return {}

    files = sorted(
        (
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("type") == "file"
            and str(entry.get("name", "")).endswith(".json")
            and entry.get("download_url")
            and entry.get("sha")
        ),
        key=lambda entry: entry["name"],
        reverse=True,  # file names are ISO dates, so this is newest first
    )[:max_files]

    records: dict[pd.Timestamp, Commentary] = {}
    for entry in files:
        sha = entry["sha"]
        if sha not in _BY_SHA:
            reply = _get(entry["download_url"], raw_headers, timeout)
            _check(reply)
            _BY_SHA[sha] = _parse_text(reply.text)
        record = _BY_SHA[sha]
        if record is not None:
            records[record.report_date] = record
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
