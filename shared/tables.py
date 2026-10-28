"""Long / Short / Net tables, drawn as HTML.

Streamlit's grid cannot merge header cells, so the three-level layout from the
spreadsheet mock-up (trader category spanning Long | Short | Net) is built here
as a small HTML table. Cells are shaded by size on the same grey-to-blue scale
as the rest of the dashboard; the number keeps its own sign.
"""

from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st
from matplotlib.colors import to_hex, to_rgb

from shared import theme

INK = "#1b1f24"
MUTED_TEXT = "#8a919a"

# Which measures get an explicit "+" on positive numbers. Long and Short are
# counts that can never be negative, so a "+" there carries no information.
DEFAULT_SIGNED = ("Net",)
ALL_SIGNED = ("Long", "Short", "Net")


# --------------------------------------------------------------------------
# colour
# --------------------------------------------------------------------------
def _luminance(rgb) -> float:
    def linear(channel: float) -> float:
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: float, b: float) -> float:
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


def _text_colour(background_rgb) -> str:
    """Whichever of white or ink reads better on this background."""
    lum = _luminance(background_rgb)
    return "#ffffff" if _contrast(1.0, lum) > _contrast(_luminance(to_rgb(INK)), lum) else INK


def limits_for(*frames: pd.DataFrame | None) -> dict[str, float]:
    """Top of the colour scale per measure.

    Long and Short share one scale (both are gross positions); Net has its own,
    because it is usually far smaller than gross and would otherwise look pale.
    Pass several frames to give them a common scale.
    """
    gross, net = 0.0, 0.0
    for frame in frames:
        if frame is None or frame.empty:
            continue
        for column in frame.columns:
            values = np.abs(frame[column].to_numpy(dtype=float))
            if not np.isfinite(values).any():
                continue
            top = float(np.nanmax(values))
            if column[1] == "Net":
                net = max(net, top)
            else:
                gross = max(gross, top)
    return {"Long": gross or 1.0, "Short": gross or 1.0, "Net": net or 1.0}


# --------------------------------------------------------------------------
# html
# --------------------------------------------------------------------------
def _format(value: float, measure: str, pct: bool, signed: tuple[str, ...]) -> str:
    if value is None or pd.isna(value):
        return "—"
    if value == 0:
        return "0.0" if pct else "0"
    plus = measure in signed
    if pct:
        return ("{:+,.1f}" if plus else "{:,.1f}").format(value)
    return ("{:+,.0f}" if plus else "{:,.0f}").format(value)


PRODUCT_PX = 150  # width of the product column
CELL_MIN_PX = 56  # narrowest a number column may get before the table scrolls
TABLE_MAX_PX = 920  # tables stop stretching here


def lsn_html(
    frame: pd.DataFrame,
    unit: str,
    limits: dict[str, float],
    signed: tuple[str, ...] = DEFAULT_SIGNED,
    max_width: int | None = TABLE_MAX_PX,
) -> str:
    """The table as one line of HTML (no indentation, so Markdown leaves it alone).

    Columns are laid out with fixed widths: the product column is a set size and
    the number columns share the rest equally. Tables with the same columns
    therefore line up exactly, whatever numbers they hold.
    """
    if frame is None or frame.empty:
        return ""
    pct = unit.startswith("%")
    columns = list(frame.columns)

    group_starts = {i for i, (cat, _) in enumerate(columns) if i == 0 or columns[i - 1][0] != cat}
    groups: list[tuple[str, int]] = []
    for cat, _ in columns:
        if groups and groups[-1][0] == cat:
            groups[-1] = (cat, groups[-1][1] + 1)
        else:
            groups.append((cat, 1))

    head1 = '<th class="corner" rowspan="2">Product</th>' + "".join(
        f'<th class="grp gstart" colspan="{span}">{html.escape(str(cat))}</th>'
        for cat, span in groups
    )
    head2 = "".join(
        f'<th class="sub{" gstart" if i in group_starts else ""}">{html.escape(measure)}</th>'
        for i, (_, measure) in enumerate(columns)
    )

    rows = []
    for product, values in frame.iterrows():
        cells = [f'<th class="prod">{html.escape(str(product))}</th>']
        for i, column in enumerate(columns):
            measure = column[1]
            value = values[column]
            klass = "gstart" if i in group_starts else ""
            if value is None or pd.isna(value):
                cells.append(f'<td class="{klass} na">—</td>')
                continue
            fraction = min(abs(float(value)) / limits.get(measure, 1.0), 1.0)
            rgba = theme.MAGNITUDE_CMAP(fraction)
            cells.append(
                f'<td class="{klass}" style="background:{to_hex(rgba)};'
                f'color:{_text_colour(rgba)}">{_format(value, measure, pct, signed)}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")

    widths = f'<colgroup><col style="width:{PRODUCT_PX}px">{"<col>" * len(columns)}</colgroup>'
    style = f"min-width:{PRODUCT_PX + CELL_MIN_PX * len(columns)}px"
    if max_width:
        style += f";max-width:{max_width}px"
    return (
        f'<div class="cot-wrap"><table class="cot-table" style="{style}">{widths}<thead>'
        f"<tr>{head1}</tr><tr>{head2}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def show_lsn(
    frame: pd.DataFrame,
    unit: str,
    limits: dict[str, float],
    signed: tuple[str, ...] = DEFAULT_SIGNED,
    max_width: int | None = TABLE_MAX_PX,
) -> None:
    markup = lsn_html(frame, unit, limits, signed, max_width)
    if markup:
        st.markdown(markup, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Full history table (one product, every week)
# --------------------------------------------------------------------------
def _history_cell(value: float, measure: str, pct: bool) -> tuple[str, str]:
    """(text, css class) for one cell of the history table."""
    if value is None or pd.isna(value):
        return "", "blank"
    delta = measure.endswith("Δ")
    decimals = 1 if pct and measure.split(" ")[0] != "OI" else 0
    text = f"{value:{'+' if delta else ''},.{decimals}f}"
    if delta and round(value, decimals) == 0:
        return text.lstrip("+-"), "flat"
    return text, ("up" if value > 0 else "down") if delta else ""


def history_html(table: pd.DataFrame, pct: bool = False) -> str:
    """Dates down the side; trader categories across, each with Long / Short / Net
    and (optionally) their week-on-week changes, then open interest.

    ``table`` has dates as its index (newest first) and two-level columns
    ``(group, measure)``; a measure ending in "Δ" is a change and is coloured.
    The header rows and the date column stay put while the table scrolls.
    """
    if table is None or table.empty:
        return ""
    columns = list(table.columns)
    groups: list[tuple[str, int]] = []
    for group, _ in columns:
        if groups and groups[-1][0] == group:
            groups[-1] = (group, groups[-1][1] + 1)
        else:
            groups.append((group, 1))
    starts = {i for i, (g, _) in enumerate(columns) if i == 0 or columns[i - 1][0] != g}

    head1 = '<th class="hd date" rowspan="2">Date</th>' + "".join(
        f'<th class="hd grp" colspan="{span}">{html.escape(str(group))}</th>' for group, span in groups
    )
    head2 = "".join(
        f'<th class="hd sub{" gs" if i in starts else ""}">{html.escape(measure)}</th>'
        for i, (_, measure) in enumerate(columns)
    )
    body = []
    for stamp, values in table.iterrows():
        cells = [f'<th class="d">{pd.Timestamp(stamp):%d %b %Y}</th>']
        for i, column in enumerate(columns):
            text, klass = _history_cell(values[column], column[1], pct)
            cells.append(f'<td class="{klass}{" gs" if i in starts else ""}">{text}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="cot-hist-wrap"><table class="cot-hist"><thead>'
        f"<tr>{head1}</tr><tr>{head2}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


# --------------------------------------------------------------------------
# Compact EIA stocks table
# --------------------------------------------------------------------------
# (column, number format, starts a new block, header text[, % column]). A block break
# draws a vertical line. With a % column the cell shows both, e.g. "-0.5 (-0.1%)", and is
# shaded by the percentage. "chg %" beside an average is how far the level is from it.
STOCK_COLUMNS = (
    ("Level", "{:,.1f}", False, "Level"), ("Week change", "{:+,.1f}", False, "Week chg"),
    ("YoY change", "{:+,.1f}", False, "YoY chg"),
    ("1y avg", "{:,.1f}", True, "1y avg"), ("vs 1y avg %", "{:+,.1f}%", False, "chg %"),
    ("1y high", "{:,.1f}", False, "1y high"), ("1y low", "{:,.1f}", False, "1y low"),
    ("5y avg", "{:,.1f}", True, "5y avg"), ("vs 5y avg %", "{:+,.1f}%", False, "chg %"),
    ("5y high", "{:,.1f}", False, "5y high"), ("5y low", "{:,.1f}", False, "5y low"),
)
# The change in level between the two dates, and the same move in percent.
STOCK_CHANGE_COLUMNS = (
    ("Change", "{:+,.1f}", False, "Δ"), ("Change %", "{:+,.1f}%", False, "Δ%"),
)


def delta_pct(value: float) -> str:
    """A percentage change written the same way everywhere: "-8.2%"."""
    return f"{0.0 if round(float(value), 1) == 0 else float(value):+.1f}%"


STOCK_CELL_MIN_PX = 64
STOCK_PRODUCT_PX = 130
STOCK_COMBO_PX = 122  # a cell holding a number and its % change


def _stock_group(column: str, unit: str) -> tuple[str, str]:
    """Cells are shaded against others in the same column and unit (barrels and Bcf differ)."""
    return (column, "pct" if column.endswith("%") else str(unit))


def stock_limits(*frames: pd.DataFrame | None) -> dict[tuple[str, str], float]:
    """Top of the shading scale per (column, unit), shared by the tables given."""
    limits: dict[tuple[str, str], float] = {}
    for frame in frames:
        if frame is None or frame.empty:
            continue
        for column in frame.columns:
            if column in ("Series", "Unit", "Week ending"):
                continue
            for unit, value in zip(frame["Unit"], frame[column]):
                if pd.notna(value):
                    key = _stock_group(column, unit)
                    limits[key] = max(limits.get(key, 0.0), abs(float(value)))
    return limits


def stocks_html(
    table: pd.DataFrame,
    max_width: int | None = None,
    columns: tuple = STOCK_COLUMNS,
    limits: dict | None = None,
) -> str:
    """Stocks, one row per series, in the same look as the position tables.

    ``table`` comes from analytics.storage.as_of_table(): Series, Unit, then the numbers.
    Pass ``limits`` (see stock_limits) to share one shading scale across tables. Gas is
    in Bcf and says so in its row label; the oil rows are in mbbls (see the heading).
    """
    if table is None or table.empty:
        return ""
    limits = limits if limits is not None else stock_limits(table)
    head = '<th class="corner">Series</th>' + "".join(
        f'<th class="sub{" gstart" if i == 0 or column[2] else ""}">'
        f"{html.escape(column[3])}</th>"
        for i, column in enumerate(columns)
    )
    rows = []
    for _, row in table.iterrows():
        label = str(row["Series"]) + (" (Bcf)" if row["Unit"] == "bcf" else "")
        cells = [f'<th class="prod">{html.escape(label)}</th>']
        for i, column in enumerate(columns):
            name, fmt, block = column[0], column[1], column[2]
            pct_name = column[4] if len(column) > 4 else None
            value = row[name]
            klass = "gstart" if i == 0 or block else ""
            if pd.isna(value):
                cells.append(f'<td class="{klass} na">—</td>')
                continue
            text = fmt.format(0.0 if round(float(value), 1) == 0 else value)
            shade_name, shade_value = name, value
            if pct_name is not None and pd.notna(row[pct_name]):
                text += f" ({delta_pct(row[pct_name])})"
                shade_name, shade_value = pct_name, row[pct_name]
            top = limits.get(_stock_group(shade_name, row["Unit"])) or 1.0
            rgba = theme.STOCK_CMAP(min(abs(float(shade_value)) / top, 1.0))
            cells.append(
                f'<td class="{klass}" style="background:{to_hex(rgba)};color:{_text_colour(rgba)}">{text}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    cell_px = [STOCK_COMBO_PX if len(column) > 4 else STOCK_CELL_MIN_PX for column in columns]
    widths = (
        f'<colgroup><col style="width:{STOCK_PRODUCT_PX}px">'
        + "".join(f'<col style="width:{px}px">' if len(column) > 4 else "<col>"
                  for px, column in zip(cell_px, columns))
        + "</colgroup>"
    )
    style = f"min-width:{STOCK_PRODUCT_PX + sum(cell_px)}px"
    if max_width:
        style += f";max-width:{max_width}px"
    return (
        f'<div class="cot-wrap"><table class="cot-table" style="{style}">{widths}<thead>'
        f"<tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )
