"""Visual language for the dashboard.

One diverging scale carries the only thing that matters at a glance — whether
a book is net long or net short, and by how much. Everything else stays
neutral so the numbers lead.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.colors import LinearSegmentedColormap

SHORT = "#a8321c"
LONG = "#12506f"
NEUTRAL = "#f4f2ee"
INK = "#1b1f24"
MUTED = "#6b7280"

PRODUCT_COLORS = [
    "#12506f",
    "#c2571a",
    "#0b6e6e",
    "#8a6d1f",
    "#7b3f8f",
    "#2f7a3d",
    "#a8321c",
    "#4b5563",
]

# EIA stock tables: the blue scale above with its hue turned to green, so lightness and
# saturation step the same way and the two sets of tables look like a pair.
def _recolour(cmap, hue: float, softness: float = 0.5) -> LinearSegmentedColormap:
    import colorsys

    from matplotlib.colors import to_hex

    shades = []
    for position in (0.0, 0.25, 0.5, 0.75, 1.0):
        h, lightness, saturation = colorsys.rgb_to_hls(*cmap(position)[:3])
        # Green looks more vivid than blue at equal saturation, so tone it down; lift the
        # darkest shades a little so they stay green rather than near-black.
        lightness += 0.05 if lightness < 0.4 else 0.0
        shades.append(to_hex(colorsys.hls_to_rgb(hue, lightness, saturation * softness)))
    return LinearSegmentedColormap.from_list("stock_green", shades)


NET_COLORSCALE = [[0.0, SHORT], [0.5, NEUTRAL], [1.0, LONG]]
NET_CMAP = LinearSegmentedColormap.from_list("cot_net", [SHORT, NEUTRAL, LONG])

# Table shading: one hue. Light grey at zero, deepening to blue as the size of
# the number grows. Sign is carried by the number itself, not by the colour.
MAGNITUDE_CMAP = LinearSegmentedColormap.from_list(
    "cot_magnitude", ["#e8ebee", "#a9bfcf", "#5f8aa6", "#12506f", "#0a3249"]
)
# Missing values must stay blank: matplotlib's default "bad" colour is
# transparent, which pandas turns into solid black.
MAGNITUDE_CMAP.set_bad("#ffffff")
STOCK_CMAP = _recolour(MAGNITUDE_CMAP, 135 / 360)


# EIA stocks tables: the same idea in olive, so the two data sets read as different things.
OLIVE_CMAP = LinearSegmentedColormap.from_list(
    "eia_olive", ["#eef0e6", "#cfd6ac", "#a5b26e", "#72823c", "#434e1f"]
)


def product_color(products: list[str]) -> dict[str, str]:
    return {p: PRODUCT_COLORS[i % len(PRODUCT_COLORS)] for i, p in enumerate(products)}


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------
def fmt_int(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value:,.0f}"


def fmt_signed(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value:+,.0f}"


def fmt_pct(value, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value:,.{decimals}f}%"


def fmt_signed_pct(value, decimals: int = 1) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "—"
    return f"{value:+,.{decimals}f} pp"


def number_format(unit: str) -> str:
    return "{:,.1f}" if unit.startswith("%") else "{:,.0f}"


def unit_suffix(unit: str) -> str:
    return "% of OI" if unit.startswith("%") else "contracts"


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------
def _limit(frame: pd.DataFrame, vmax: float | None = None) -> float:
    """Largest absolute value in the table — the top of the colour scale."""
    if vmax:
        return float(vmax)
    numeric = frame.select_dtypes("number")
    if numeric.empty:
        return 1.0
    values = np.abs(numeric.to_numpy(dtype=float))
    top = float(np.nanmax(values)) if np.isfinite(values).any() else 1.0
    return top or 1.0


def shared_limit(*frames: pd.DataFrame) -> float:
    """One scale for several tables, so equal numbers get equal shades."""
    return max((_limit(f) for f in frames if f is not None and not f.empty), default=1.0)


def _magnitude_style(frame: pd.DataFrame, number_fmt: str, vmax: float | None):
    numeric_columns = list(frame.select_dtypes("number").columns)
    styler = frame.style.format(number_fmt, na_rep="—")
    if numeric_columns:
        styler = styler.background_gradient(
            cmap=MAGNITUDE_CMAP,
            gmap=frame[numeric_columns].abs(),
            vmin=0,
            vmax=_limit(frame, vmax),
            axis=None,
            subset=numeric_columns,
        )
    return styler.set_properties(**{"font-size": "13px"})


def diverging_table(
    frame: pd.DataFrame,
    unit: str = "Contracts",
    symmetric: bool = True,  # kept for callers; the scale is now magnitude-only
    vmax: float | None = None,
    signed: bool = False,
):
    """Level table: shade by size (grey -> blue), numbers keep their sign.

    ``signed=True`` puts an explicit "+" on positive numbers (used for net).
    """
    if frame.empty:
        return frame
    if signed:
        fmt = "{:+,.1f}" if unit.startswith("%") else "{:+,.0f}"
    else:
        fmt = number_format(unit)
    return _magnitude_style(frame, fmt, vmax)


def signed_table(frame: pd.DataFrame, unit: str = "Contracts", vmax: float | None = None):
    """Change table: same shading, explicit +/- on every number."""
    if frame.empty:
        return frame
    fmt = "{:+,.1f}" if unit.startswith("%") else "{:+,.0f}"
    return _magnitude_style(frame, fmt, vmax)


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------
def layout(fig: go.Figure, height: int = 420, legend_title: str | None = None) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=36, b=8),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color=INK, size=13),
        hovermode="x unified",
        legend=dict(
            title=legend_title or "",
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
    )
    fig.update_xaxes(showgrid=False, linecolor="#d5d8dc", ticks="outside", tickcolor="#d5d8dc")
    fig.update_yaxes(gridcolor="#eceef1", zeroline=True, zerolinecolor="#b6bcc4", zerolinewidth=1)
    return fig


# --------------------------------------------------------------------------
# Streamlit compatibility
# --------------------------------------------------------------------------
def wide() -> dict:
    """Full-width kwargs for st.dataframe / st.plotly_chart across versions."""
    import streamlit as st

    try:
        major, minor = (int(part) for part in st.__version__.split(".")[:2])
    except ValueError:  # pragma: no cover - unusual dev builds
        return {"width": "stretch"}
    return {"width": "stretch"} if (major, minor) >= (1, 49) else {"use_container_width": True}


# --------------------------------------------------------------------------
# Page chrome
# --------------------------------------------------------------------------
SIDEBAR_WIDTH = "17rem"  # Streamlit's default is about 21rem
GREETING_FONT = "Source Serif 4"  # Google font for the greeting
TITLE_FONT = "Plus Jakarta Sans"  # Google font for the calendar titles
TEXT_PX = 12.5  # table and commentary body text
HEAD_PX = 16  # commentary headings: three steps above the body
UP_COLOUR = "#1a7f37"  # week-on-week increases in the history table
DOWN_COLOUR = "#c0392b"  # decreases

PAGE_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family={GREETING_FONT.replace(' ', '+')}:ital,wght@0,400;0,500;1,400&family={TITLE_FONT.replace(' ', '+')}:wght@400;500;700&display=swap');
.block-container, [data-testid="stMainBlockContainer"] {{
    /* Top padding must clear Streamlit's fixed toolbar (about 3.75rem), or the
       header row's labels slide underneath it. */
    padding: 4.25rem 1.4rem 2rem 1.4rem !important;
    max-width: 100% !important;
}}
[data-testid="stSidebar"][aria-expanded="true"] {{
    min-width: {SIDEBAR_WIDTH} !important;
    max-width: {SIDEBAR_WIDTH} !important;
    width: {SIDEBAR_WIDTH} !important;
}}
[data-testid="stSidebarUserContent"] {{ padding: 1rem 0.9rem 1.5rem 0.9rem; }}

/* Long / Short / Net tables (see ui/tables.py) */
.cot-wrap {{ overflow-x: auto; margin: 0 0 0.7rem 0; }}
.cot-wrap table.cot-table {{
    border-collapse: separate; border-spacing: 0; width: 100%; margin: 0;
    table-layout: fixed; font-size: {TEXT_PX}px; font-variant-numeric: tabular-nums;
}}
.cot-wrap table.cot-table th, .cot-wrap table.cot-table td {{
    padding: 3px 6px !important; white-space: nowrap; border: 0 !important;
    background-clip: padding-box;
}}
.cot-wrap table.cot-table thead th {{
    text-align: center; font-weight: 600; background: transparent !important;
    border-bottom: 1px solid rgba(128,128,128,.35) !important;
}}
.cot-wrap table.cot-table thead th.sub {{ font-weight: 500; opacity: .8; }}
.cot-wrap table.cot-table thead th.corner {{ text-align: left; vertical-align: bottom; }}
.cot-wrap table.cot-table th.prod {{
    text-align: left; font-weight: 500; padding-right: 12px !important;
    background: transparent !important; white-space: normal;
}}
.cot-wrap table.cot-table td {{ text-align: right; }}
.cot-wrap table.cot-table td.na {{ color: #8a919a; text-align: center; }}
.cot-wrap table.cot-table .gstart {{ border-left: 1px solid rgba(128,128,128,.45) !important; }}
.cot-wrap table.cot-table thead th.corner.gstart {{ border-left: 0 !important; }}

/* Weekly notes: a title over a grid of equal-height cards (see ui/notes.py).
   Body text matches the tables; headings are three sizes up. */
.cot-note {{ font-size: {TEXT_PX}px; line-height: 1.5; margin-bottom: 0.8rem; }}
.cot-note-title {{ font-size: {HEAD_PX}px; font-weight: 700; line-height: 1.3; margin: 0.2rem 0 0.7rem 0; }}
.sec-rule {{ border: 0; border-top: 1px solid rgba(128,128,128,.4); margin: 0 0 1.1rem 0; }}
.sec-gap {{ height: calc(1.6rem + 2cm); }}
.sec-title {{ font-size: 20px; font-weight: 700; line-height: 1.3; margin: 0 0 0.6rem 0; }}
.cot-note a {{ color: inherit; text-decoration: underline; }}
.cot-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.7rem; align-items: stretch; }}
.cot-card {{ border: 1px solid rgba(128,128,128,.3); border-radius: 8px; padding: 0.65rem 0.85rem 0.45rem 0.85rem; }}
.cot-card-title {{ font-size: {HEAD_PX}px; font-weight: 700; line-height: 1.3; margin-bottom: 0.4rem; }}
.cot-note p, .cot-note li, .cot-card p, .cot-card li {{ font-size: {TEXT_PX}px; line-height: 1.5; margin: 0 0 0.5rem 0; }}
.cot-note ul, .cot-card ul {{ margin: 0 0 0.5rem 0; padding-left: 1.1rem; }}

/* Full history table (see tables.history_html): scrolls inside its own box, with
   the header rows and the date column pinned. Fixed colours, so it reads the same
   in light and dark mode. */
.cot-hist-wrap {{ overflow: auto; max-height: 72vh; border: 1px solid #d5d8dc; border-radius: 6px; background: #fff; }}
table.cot-hist {{ border-collapse: separate; border-spacing: 0; width: max-content; margin: 0;
    font-size: {TEXT_PX}px; font-variant-numeric: tabular-nums; color: #1b1f24; }}
table.cot-hist th, table.cot-hist td {{ padding: 4px 9px !important; border: 0 !important; white-space: nowrap; text-align: right; }}
table.cot-hist thead th.hd {{ position: sticky; background: #12304a !important; color: #fff !important; text-align: center; font-weight: 600; height: 26px; line-height: 18px; box-sizing: border-box; }}
table.cot-hist thead tr:first-child th.hd {{ top: 0; z-index: 3; }}
table.cot-hist thead tr:nth-child(2) th.hd {{ top: 26px; z-index: 3; background: #1f4a6e !important; font-weight: 500; min-width: 66px; }}
table.cot-hist thead th.hd.date {{ left: 0; z-index: 4; text-align: left; min-width: 96px; }}
table.cot-hist thead th.grp {{ border-left: 1px solid rgba(255,255,255,.35) !important; }}
table.cot-hist th.gs, table.cot-hist td.gs {{ border-left: 1px solid #c4cad1 !important; }}
table.cot-hist th.gs2, table.cot-hist td.gs2 {{ border-left: 2px solid #5b6672 !important; }}
table.cot-hist thead th.gs2 {{ border-left: 2px solid rgba(255,255,255,.6) !important; }}
table.cot-hist thead th.sub.gs {{ border-left: 1px solid rgba(255,255,255,.35) !important; }}
table.cot-hist tbody th.d {{ position: sticky; left: 0; z-index: 2; background: #fff !important; text-align: left; font-weight: 600; }}
table.cot-hist tbody tr:nth-child(even) th.d, table.cot-hist tbody tr:nth-child(even) td {{ background: #f4f6f8; }}
table.cot-hist td.up {{ color: {UP_COLOUR}; }}
table.cot-hist td.down {{ color: {DOWN_COLOUR}; }}
table.cot-hist td.flat {{ color: #8a919a; }}
/* Home page. One palette: olive for the greeting panel, accents, headers and
   underlines, warm sand for table bands. Greeting in GREETING_FONT (a serif), calendar titles in
   TITLE_FONT. Any Google font name works. */
.hello {{ background: linear-gradient(120deg, #eef1e3 0%, #e3e9d3 100%); border-left: 6px solid #4d5a32; border-radius: 10px;
    padding: 1.3rem 1.7rem 1.1rem 1.6rem; margin: 0 0 1.6rem 0; }}
.hello-head {{ font-family: '{GREETING_FONT}', Georgia, serif; font-size: 32px; font-weight: 500;
    line-height: 1.2; letter-spacing: -0.01em; color: #2f3a22; }}
.hello-aside {{ font-family: '{GREETING_FONT}', Georgia, serif; font-size: 18px; font-style: italic;
    color: #4d5a32; margin-top: .35rem; }}
.hello-time {{ font-size: 13px; color: #6b7280; margin-top: .55rem; }}
.cal-title {{ font-family: '{TITLE_FONT}', 'Segoe UI', sans-serif; font-size: 16px; font-weight: 700; color: #3b4626;
    padding-bottom: .2rem; margin: 0 0 .55rem 0; border-bottom: 3px solid #4d5a32; display: inline-block; }}
.cal-note {{ font-size: 12px; color: #6b7280; margin: .35rem 0 1.4rem 0; }}
.cal-wrap {{ overflow: auto; border-radius: 8px; }}
table.cal {{ border-collapse: separate; border-spacing: 0; width: 100%; font-size: 13px; color: #1b1f24; }}
table.cal th {{ position: sticky; top: 0; z-index: 1; background: #4d5a32; color: #f6f1e1; font-weight: 700;
    text-align: left; padding: 7px 10px; border: 0; }}
table.cal td {{ padding: 6px 10px; border: 0; white-space: normal; vertical-align: top; }}
table.cal td:first-child, table.cal td:last-child {{ white-space: nowrap; }}
table.cal tbody tr:nth-child(even) td {{ background: #f4f1e4; }}
table.cal tbody tr:nth-child(odd) td {{ background: #ffffff; }}
table.cal td.soon {{ color: #4d5a32; font-weight: 700; }}
@media (max-width: 1100px) {{ .cot-grid {{ grid-template-columns: 1fr; }} }}
</style>
"""


def inject_css() -> None:
    import streamlit as st

    st.markdown(PAGE_CSS, unsafe_allow_html=True)
