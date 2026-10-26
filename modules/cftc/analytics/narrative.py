"""Turns the dashboard's own numbers into an analysis prompt.

Pure text-building: takes the summary frame (``cot.summarise`` output) and
returns strings. The model call lives in ``sources/llm.py``.
"""

from __future__ import annotations

import math

import pandas as pd


def _n(value) -> str:
    return "n/a" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value:,.0f}"


def _s(value) -> str:
    return "n/a" if value is None or (isinstance(value, float) and math.isnan(value)) else f"{value:+,.0f}"


def data_block(summary: pd.DataFrame, labels: dict[str, str], max_rows: int) -> tuple[str, int]:
    """One block per product, one line per trader category.

    Returns the text and how many product x category rows were left out to stay
    under ``max_rows`` (largest open interest is kept).
    """
    if summary.empty:
        return "", 0
    order = (
        summary.groupby("product")["open_interest"].max().sort_values(ascending=False).index
    )
    lines: list[str] = []
    used = 0
    omitted = 0
    for product in order:
        rows = summary[summary["product"].eq(product)]
        if used + len(rows) > max_rows:
            omitted += len(rows)
            continue
        used += len(rows)
        first = rows.iloc[0]
        lines.append(
            f"\n{product} (OI: {_n(first['open_interest'])}, "
            f"change in OI: {_s(first.get('oi_chg_base'))}):"
        )
        for row in rows.itertuples():
            label = labels.get(row.category, row.category)
            index = "" if pd.isna(row.cot_index) else f" | COT index {row.cot_index:.0f}"
            zscore = "" if pd.isna(row.net_z) else f", z {row.net_z:+.1f}"
            lines.append(
                f"  {label}: L={_n(row.long)} S={_n(row.short)} Net={_n(row.net)} "
                f"(ΔNet={_s(row.net_chg_base)}; ΔL={_s(row.long_chg_base)}, "
                f"ΔS={_s(row.short_chg_base)}){index}{zscore}"
            )
    return "\n".join(lines).strip("\n"), omitted


def news_prompt(start: str, end: str) -> str:
    return f"""Search for news published between {start} and {end} on the following topics and return a concise summary of the key developments:

1. Crude oil market news — Brent and WTI price moves, any significant rallies or selloffs and their drivers
2. OPEC+ — any production decisions, quota changes, compliance issues, or member commentary
3. US EIA inventory data — weekly crude, gasoline, and distillate inventory changes (draws or builds)
4. Oil demand — China demand outlook, global refinery runs, any demand surprises
5. Geopolitical factors — anything affecting oil supply (Middle East tensions, Russia/Ukraine, sanctions, shipping disruptions)
6. Macro backdrop — US dollar direction, Fed rate expectations, and how they are influencing oil positioning

Only use sources dated inside that period. For each topic, give 2-3 bullet points of the most important developments. Be specific — include price levels, inventory figures in millions of barrels, and named officials or countries where relevant. If a topic has nothing in that period, say so in one line."""


def build_prompt(
    data: str,
    as_of: str,
    baseline: str,
    weeks: int,
    basis: str,
    report: str,
    news: str = "",
    omitted: int = 0,
) -> str:
    span = "week-on-week" if weeks == 1 else f"over the {weeks} weeks"
    news_section = f"\nMARKET NEWS FOR THE PERIOD:\n{news}\n" if news.strip() else ""
    trimmed = (
        f"\n({omitted} smaller product/category rows were left out to keep this short.)\n"
        if omitted
        else ""
    )
    news_instruction = (
        "use the market and macro context above to explain the positioning moves — "
        "explicitly connect OPEC+ decisions, inventory data, demand signals, "
        "geopolitical developments, and dollar/rates direction to what speculators "
        "and commercials are doing"
        if news.strip()
        else "write a concise two-liner on the fundamental backdrop based on positioning "
        "signals alone. Do not flag caveats or suggest caution about missing data."
    )
    return f"""You are a senior commodities analyst covering energy markets with deep knowledge of oil market fundamentals and macro drivers.

Analyse the CFTC {report} COT data below ({basis}). Compare positions on {as_of} with {baseline} ({span}) and write a
sharp, professional commentary (max 350 words) for a petroleum trading desk audience.
The change columns (ΔNet, ΔL, ΔS) are {as_of} minus {baseline}. COT index runs 0 (most net short in its window) to 100 (most net long).

COT DATA:
{data}
{trimmed}{news_section}
Structure your commentary with these sections:
🔑 Key Positioning Shifts — the biggest moves between the two dates, especially Managed Money. Use specific numbers. Note any divergences between crude benchmarks or between crude and products.
⚖️ Physical vs Financial — divergences between Prod/Merch hedgers and Managed Money/Swaps. Are commercials hedging into strength or weakness?
🌐 Macro & Fundamentals — {news_instruction}. Be specific about cause and effect.
⚡ Risk Outlook — given positioning, state the near-term price risk. Flag any crowded positioning risk or potential for a sharp positioning unwind.

Be direct and actionable. No waffle. Use specific numbers from the data. Only discuss products and categories that appear in the data above."""
