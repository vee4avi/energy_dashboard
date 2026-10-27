"""The main panel: one function per tab."""

from __future__ import annotations


import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from modules.cftc import services
from modules.cftc.analytics import cot
from modules.cftc.analytics import storage as storage_stats
from modules.cftc.config import settings
from modules.cftc.sources import commentary, eia
from shared import notes, state, tables, theme
from modules.cftc.ui.filters import Filters

PRESET_OFFSETS = {"Last week": 1, "4 weeks ago": 4, "13 weeks ago": 13, "1 year ago": 52}
KPI_PER_ROW = 6


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def category_labels(report: str) -> dict[str, str]:
    return {c.key: c.ui_label for c in settings.categories_for(report)}


def _label_columns(table: pd.DataFrame, report: str) -> pd.DataFrame:
    return table.rename(columns=category_labels(report))


def _date_options(frame: pd.DataFrame) -> list[pd.Timestamp]:
    return cot.report_dates(frame)


def _fmt_date(value) -> str:
    return pd.Timestamp(value).strftime("%d %b %Y")


def _offset_date(dates: list[pd.Timestamp], anchor: pd.Timestamp, weeks: int):
    """The report date `weeks` reports before `anchor` (dates are newest first)."""
    if anchor not in dates:
        return None
    position = dates.index(anchor) + weeks
    return dates[position] if position < len(dates) else None


def _value_frame(frame: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    return frame[frame["category"].isin(filters.categories)]


def empty_state(message: str) -> None:
    st.info(message)


def _note(text: str) -> None:
    """Commentary as a title over a grid of cards; plain Markdown if it has no sections."""
    markup = notes.note_html(text)
    if markup:
        st.markdown(markup, unsafe_allow_html=True)
    else:
        st.markdown(f"<div class='cot-note'>{notes.body_html(text)}</div>", unsafe_allow_html=True)


def _stamp(iso: str) -> str:
    try:
        return pd.Timestamp(iso).strftime("%d %b %Y %H:%M UTC")
    except (ValueError, TypeError):
        return ""


# --------------------------------------------------------------------------
# Commentary: saved from the Telegram bot, and run on demand
# --------------------------------------------------------------------------
def commentary_panel(record: commentary.Commentary, filters: Filters) -> None:
    """The bot's weekly commentary, exactly as it was written."""
    basis_label = settings.BASIS_LABELS.get(record.basis, record.basis)
    with st.container(border=True):
        st.markdown("**Desk commentary**")
        st.caption(
            f"{_fmt_date(record.report_date)} vs {_fmt_date(record.prior_date)} · "
            f"week-on-week · {basis_label}"
        )
        if record.basis != filters.basis:
            viewing = settings.BASIS_LABELS.get(filters.basis, filters.basis)
            st.info(
                f"Written on {basis_label.lower()} data. You are viewing "
                f"{viewing.lower()}, so figures quoted here can differ from the tables.",
                icon="ℹ️",
            )
        _note(record.text)
        details = [part for part in (_stamp(record.generated_at), record.model) if part]
        if details:
            st.caption("Generated " + " · ".join(details))
        if record.products:
            st.caption("Covers: " + ", ".join(record.products))
        if record.news:
            with st.expander("News behind this commentary"):
                st.markdown(
                    f"<div class='cot-note'>{notes.body_html(record.news)}</div>", unsafe_allow_html=True
                )


# --------------------------------------------------------------------------
# 1. Snapshot
# --------------------------------------------------------------------------
def snapshot_tab(frame: pd.DataFrame, filters: Filters) -> None:
    dates = _date_options(frame)
    if not dates:
        return empty_state("No report dates in the loaded history.")

    controls = st.columns([2, 2, 3])
    state.ensure_option("snap_as_of", dates)
    as_of = controls[0].selectbox(
        "Report date", options=dates, format_func=_fmt_date, key="snap_as_of"
    )
    baseline_choice = controls[1].selectbox(
        "Compare against",
        options=list(PRESET_OFFSETS) + ["Pick a date"],
        key="snap_baseline_choice",
    )
    if baseline_choice == "Pick a date":
        older = [d for d in dates if d < as_of]
        state.ensure_option("snap_baseline_date", older)
        baseline = controls[2].selectbox(
            "Baseline date", options=older, format_func=_fmt_date, key="snap_baseline_date"
        ) if older else None
    else:
        baseline = _offset_date(dates, as_of, PRESET_OFFSETS[baseline_choice])
        controls[2].markdown(
            f"<div style='padding-top:1.8rem;color:{theme.MUTED}'>Baseline: "
            f"{_fmt_date(baseline) if baseline is not None else 'not available'}</div>",
            unsafe_allow_html=True,
        )

    view = _value_frame(frame, filters)
    snapshot = cot.as_of_slice(view, as_of)
    base_slice = cot.as_of_slice(view, baseline) if baseline is not None else pd.DataFrame()
    summary = cot.summarise(snapshot, base_slice)
    if summary.empty:
        return empty_state("Nothing to show for this date — widen the filters.")

    labels = category_labels(filters.report)
    pct = filters.unit.startswith("%")
    value_col = filters.value_column
    change_col = "net_pct_oi_chg_base" if pct else "net_chg_base"

    # Headline numbers: one participant at a time, chosen here.
    if filters.categories:
        state.ensure_option("kpi_category", filters.categories)
        primary = st.radio(
            "Headline participant",
            options=filters.categories,
            format_func=lambda key: labels.get(key, key),
            horizontal=True,
            key="kpi_category",
            help="Switches the headline net-position numbers between trader categories.",
        )
        headline = summary[summary["category"].eq(primary)].sort_values(
            "open_interest", ascending=False
        )
        st.markdown(f"**{labels.get(primary, primary)} — net position**")
        for start in range(0, len(headline), KPI_PER_ROW):
            row_columns = st.columns(KPI_PER_ROW)
            for column, row in zip(row_columns, headline.iloc[start : start + KPI_PER_ROW].itertuples()):
                value = getattr(row, value_col)
                delta = getattr(row, change_col, float("nan"))
                column.metric(
                    row.product,
                    theme.fmt_pct(value) if pct else theme.fmt_int(value),
                    theme.fmt_signed_pct(delta) if pct else theme.fmt_signed(delta),
                )

    st.divider()

    unit_note = theme.unit_suffix(filters.unit)
    current = cot.long_short_net(snapshot, filters.categories, pct, labels)
    have_baseline = baseline is not None and not base_slice.empty
    if have_baseline:
        # Same rows and columns as the current table, so the two line up.
        earlier = cot.long_short_net(base_slice, filters.categories, pct, labels).reindex(
            index=current.index, columns=current.columns
        )
        change = current - earlier
    else:
        earlier = change = pd.DataFrame()

    # One colour scale across both position tables: equal numbers, equal shades.
    scale = tables.limits_for(current, earlier)

    def show_current() -> None:
        st.markdown(f"**{_fmt_date(as_of)}** · positions, {unit_note}")
        tables.show_lsn(current, filters.unit, scale)

    def show_earlier() -> None:
        if not have_baseline:
            st.markdown(f"**Baseline** · positions, {unit_note}")
            st.info("No earlier report is available for that comparison.")
            return
        st.markdown(f"**{_fmt_date(baseline)}** · positions, {unit_note}")
        tables.show_lsn(earlier, filters.unit, scale)

    def show_change() -> None:
        if have_baseline:
            st.markdown(
                f"**Change** · {_fmt_date(as_of)} vs {_fmt_date(baseline)}, {unit_note}"
            )
            tables.show_lsn(
                change, filters.unit, tables.limits_for(change), signed=tables.ALL_SIGNED
            )

    # Saved bot commentary describes one pair of dates: this report and the week
    # before. Any other comparison gets none, and a hint says why.
    records, commentary_note = services.load_commentary()
    if commentary_note:
        st.caption(f"⚠️ {commentary_note}")
    saved = commentary.match(records, as_of, baseline, filters.report)
    if saved is None and have_baseline:
        other = commentary.for_date(records, as_of, filters.report)
        if other is not None:
            st.caption(
                f"💬 Saved commentary exists for {_fmt_date(as_of)} against "
                f"{_fmt_date(other.prior_date)}. Set “Compare against” to Last week to see it."
            )
    if not records:
        st.caption(
            "💬 No commentary yet: put the bot's weekly .json files in the dashboard's "
            "`commentary` folder."
        )

    if saved is not None:
        main_col, side_col = st.columns([11, 9], gap="small")
    else:
        main_col, side_col = st.container(), None

    with main_col:  # the tables are always stacked, so they keep their full width
        show_current()
        show_earlier()
        show_change()
        storage_summary(as_of, baseline if have_baseline else None)
    if side_col is not None:
        with side_col:
            commentary_panel(saved, filters)

    st.markdown(f"**Positioning extremes** · {filters.lookback}-week window")
    st.caption(
        "COT index: where this week's net position sits between its lowest (0) and "
        "highest (100) over the window. 0 is the most net short it has been, 100 the "
        "most net long. Net z-score: how many standard deviations net is from its "
        "window average. Readings above about 80 or below 20 are usually called "
        "extreme; that is a convention, not a rule."
    )
    extremes = summary[["product", "category", "cot_index", "net_z", "net_pct_oi"]].copy()
    extremes["category"] = extremes["category"].map(category_labels(filters.report))
    extremes = extremes.rename(
        columns={
            "product": "Product",
            "category": "Category",
            "cot_index": "COT index",
            "net_z": "Net z-score",
            "net_pct_oi": "Net % of OI",
        }
    )
    st.dataframe(
        extremes,
        **theme.wide(),
        hide_index=True,
        column_config={
            "COT index": st.column_config.ProgressColumn(
                "COT index",
                help="Where this week's net sits between its window low (0) and high (100).",
                min_value=0,
                max_value=100,
                format="%.0f",
            ),
            "Net z-score": st.column_config.NumberColumn(format="%.2f"),
            "Net % of OI": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )


# --------------------------------------------------------------------------
# 2. Compare dates
# --------------------------------------------------------------------------

BREAKDOWN = "Long / Short / Net"


def _short_dates(dates: list[pd.Timestamp]) -> dict[pd.Timestamp, str]:
    """Compact date labels for column headings; the year only if the dates span years."""
    one_year = len({d.year for d in dates}) == 1
    return {d: d.strftime("%d %b" if one_year else "%d %b %y") for d in dates}


def _breakdown_frames(
    view: pd.DataFrame, selected: list[pd.Timestamp], filters: Filters, delta_mode: str
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Per trader category: Long/Short/Net by date, and the change between dates.

    Both frames have products down the side and two-level columns (date, measure),
    so they draw with the same grouped tables as the Snapshot tab.
    """
    pct = filters.unit.startswith("%")
    columns = cot.measure_columns(pct)
    dates = sorted(selected)
    names = _short_dates(dates)
    labels = category_labels(filters.report)
    levels: dict[str, pd.DataFrame] = {}
    changes: dict[str, pd.DataFrame] = {}
    for category in filters.categories:
        sub = view[view["category"].eq(category) & view["report_date"].isin(dates)]
        if sub.empty:
            continue
        order = sub.groupby("product")["open_interest"].max().sort_values(ascending=False).index
        pivots = {
            measure: cot.pivot_dates(sub, dates, value=columns[measure], index=("product",)).reindex(
                order
            )
            for measure in cot.MEASURES
        }
        present = [d for d in dates if d in pivots["Net"].columns]
        level = {(names[d], m): pivots[m][d] for d in present for m in cot.MEASURES}
        label = labels.get(category, category)
        levels[label] = pd.DataFrame(level)

        delta: dict[tuple[str, str], pd.Series] = {}
        for i, later in enumerate(present[1:], start=1):
            earlier = present[0] if delta_mode == "vs first" else present[i - 1]
            for m in cot.MEASURES:
                delta[(f"{names[later]} vs {names[earlier]}", m)] = pivots[m][later] - pivots[m][earlier]
        changes[label] = pd.DataFrame(delta)
    for frame in (*levels.values(), *changes.values()):
        frame.columns = pd.MultiIndex.from_tuples(frame.columns)
        frame.index.name = "Product"
    return levels, changes


def _show_breakdown(
    levels: dict[str, pd.DataFrame],
    changes: dict[str, pd.DataFrame],
    view_mode: str,
    unit: str,
) -> None:
    show_levels = view_mode in ("Levels", "Both")
    show_changes = view_mode in ("Changes", "Both")
    unit_note = theme.unit_suffix(unit)
    if show_levels:
        scale = tables.limits_for(*levels.values())
        if view_mode == "Both":
            st.markdown(f"**Positions** · {unit_note}")
        for label, frame in levels.items():
            st.markdown(f"**{label}**")
            tables.show_lsn(frame, unit, scale, max_width=None)
    if show_changes:
        usable = {k: v for k, v in changes.items() if not v.empty}
        if not usable:
            st.info("Pick at least two dates to see changes.")
            return
        scale = tables.limits_for(*usable.values())
        st.markdown(f"**Change between the selected dates** · {unit_note}")
        for label, frame in usable.items():
            st.markdown(f"**{label}**")
            tables.show_lsn(frame, unit, scale, signed=tables.ALL_SIGNED, max_width=None)

def compare_tab(frame: pd.DataFrame, filters: Filters) -> None:
    dates = _date_options(frame)
    if len(dates) < 2:
        return empty_state("Load more history to compare dates.")

    anchor = dates[0]
    default_dates = [anchor] + [
        d
        for d in (
            _offset_date(dates, anchor, 1),
            _offset_date(dates, anchor, 4),
            _offset_date(dates, anchor, 13),
            _offset_date(dates, anchor, 52),
        )
        if d is not None
    ]

    state.prune_multiselect("compare_dates", dates)
    if not st.session_state.get("compare_dates"):
        st.session_state["compare_dates"] = default_dates

    top = st.columns([5, 2, 2, 2])
    selected = top[0].multiselect(
        "Report dates",
        options=dates,
        format_func=_fmt_date,
        key="compare_dates",
        help="Pick any number of weeks. Columns are ordered oldest to newest.",
    )
    view_mode = top[1].radio(
        "Show", options=["Levels", "Changes", "Both"], key="compare_view"
    )
    delta_mode = top[2].radio(
        "Changes measured",
        options=["vs previous", "vs first"],
        key="compare_delta",
        help="'vs previous' walks week to week; 'vs first' anchors on the oldest "
        "selected date.",
    )

    measure = top[3].radio(
        "Measure",
        options=[BREAKDOWN, *cot.MEASURES[::-1]],  # then Net, Short, Long
        index=0,
        key="compare_measure",
        help="Long / Short / Net shows all three side by side for every date, as on "
        "the Snapshot tab. Or pick one measure for a compact table.",
    )

    if len(selected) < 1:
        return empty_state("Select at least one report date.")

    grouped = measure == BREAKDOWN
    if grouped:
        measure = "Net"  # the chart below plots net
    value_col = cot.measure_columns(filters.unit.startswith("%"))[measure]
    view = _value_frame(frame, filters)
    table = cot.pivot_dates(view, selected, value=value_col)
    if table.empty:
        return empty_state("No data for that combination.")

    table = table.rename(columns=_fmt_date)
    table.index = pd.MultiIndex.from_tuples(
        [(product, category_labels(filters.report).get(cat, cat)) for product, cat in table.index],
        names=["Product", "Category"],
    )

    signed = measure == "Net"
    if grouped:
        levels, changes = _breakdown_frames(view, selected, filters, delta_mode)
        _show_breakdown(levels, changes, view_mode, filters.unit)
    elif view_mode == "Levels":
        st.dataframe(theme.diverging_table(table, filters.unit, signed=signed), **theme.wide())
    elif view_mode == "Changes":
        st.dataframe(
            theme.signed_table(cot.changes_only(table, delta_mode), filters.unit),
            **theme.wide(),
        )
    else:
        st.markdown(f"**{measure} position** · {theme.unit_suffix(filters.unit)}")
        st.dataframe(theme.diverging_table(table, filters.unit, signed=signed), **theme.wide())
        st.markdown("**Change between the selected dates**")
        st.dataframe(
            theme.signed_table(cot.changes_only(table, delta_mode), filters.unit),
            **theme.wide(),
        )

    chart_frame = view[view["report_date"].isin(selected)].copy()
    chart_frame["date_label"] = chart_frame["report_date"].map(_fmt_date)
    chart_frame["category_label"] = chart_frame["category"].map(
        category_labels(filters.report)
    )
    ordered_labels = [_fmt_date(d) for d in sorted(selected)]
    figure = px.bar(
        chart_frame,
        x="product",
        y=value_col,
        color="date_label",
        barmode="group",
        facet_col="category_label" if len(filters.categories) > 1 else None,
        facet_col_wrap=3,
        category_orders={"date_label": ordered_labels},
        color_discrete_sequence=theme.PRODUCT_COLORS,
        labels={"product": "", value_col: f"{measure.lower()}, {theme.unit_suffix(filters.unit)}"},
    )
    figure.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    figure.update_layout(hovermode="closest")
    st.plotly_chart(
        theme.layout(figure, height=200 + 180 * max(1, len(filters.categories) // 3 + 1)),
        **theme.wide(),
    )


# --------------------------------------------------------------------------
# 3. Full table
# --------------------------------------------------------------------------
HISTORY_WINDOWS = {"1 year": 52, "2 years": 104, "3 years": 156, "All loaded": None}
# Trader categories in the order the desk reads them across the table.
HISTORY_CATEGORY_ORDER = ("prod_merc", "swap", "m_money", "other_rept", "comm", "noncomm", "nonrept", "tot_rept")
HISTORY_DEFAULT_CATEGORIES = ("prod_merc", "swap", "m_money", "other_rept", "comm", "noncomm")


def history_frame(
    view: pd.DataFrame, categories: list[str], labels: dict[str, str], pct: bool, changes: bool
) -> pd.DataFrame:
    """One product, every week: dates down the side (newest first), then for each
    trader category Long / Short / Net (and week-on-week changes), then open interest.

    Changes are taken on the full history before any window is applied, so the
    oldest visible week still shows its change.
    """
    columns = cot.measure_columns(pct)
    parts: dict[tuple[str, str], pd.Series] = {}
    for category in categories:
        sub = view[view["category"].eq(category)].drop_duplicates("report_date", keep="last")
        sub = sub.set_index("report_date").sort_index()
        label = labels.get(category, category)
        for measure in cot.MEASURES:
            parts[(label, measure)] = sub[columns[measure]]
        if changes:
            for measure in cot.MEASURES:
                parts[(label, f"{measure} Δ")] = sub[columns[measure]].diff()
    oi = view.drop_duplicates("report_date", keep="last").set_index("report_date").sort_index()["open_interest"]
    parts[("Open interest", "OI")] = oi
    if changes:
        parts[("Open interest", "OI Δ")] = oi.diff()
    table = pd.DataFrame(parts)
    table.columns = pd.MultiIndex.from_tuples(table.columns)
    return table.sort_index(ascending=False)


def full_table_tab(frame: pd.DataFrame, filters: Filters) -> None:
    latest = frame.sort_values("report_date").drop_duplicates("product", keep="last")
    products = list(latest.sort_values("open_interest", ascending=False)["product"])
    if not products:
        return empty_state("No history loaded.")

    available = [c.key for c in settings.categories_for(filters.report)]
    ordered = [k for k in HISTORY_CATEGORY_ORDER if k in available] + [
        k for k in available if k not in HISTORY_CATEGORY_ORDER
    ]
    labels = category_labels(filters.report)
    defaults = [k for k in ordered if k in HISTORY_DEFAULT_CATEGORIES] or ordered[:3]

    state.ensure_option("full_product", products)
    state.prune_multiselect("full_categories", ordered)
    top = st.columns([3, 4, 2, 2])
    product = top[0].selectbox("Product", options=products, key="full_product")
    chosen = top[1].multiselect(
        "Trader categories",
        options=ordered,
        default=defaults,
        format_func=lambda key: labels.get(key, key),
        key="full_categories",
        help="Other reportable, non-reportable and total reportable can be added here.",
    )
    window = top[2].selectbox("Window", options=list(HISTORY_WINDOWS), index=len(HISTORY_WINDOWS) - 1, key="full_window")
    changes = top[3].toggle("Week-on-week changes", value=True, key="full_changes")

    if not chosen:
        return empty_state("Pick at least one trader category.")
    pct = filters.unit.startswith("%")
    view = frame[frame["product"].eq(product)]
    table = history_frame(view, [k for k in ordered if k in chosen], labels, pct, changes)
    weeks = HISTORY_WINDOWS[window]
    if weeks:
        table = table.iloc[:weeks]
    if table.empty:
        return empty_state("No data for that product.")

    exchange = str(view["exchange"].iloc[0]) if "exchange" in view else ""
    source = "ICE Futures Europe" if exchange == "IFEU" else "CFTC"
    st.markdown(f"**{source} COT {filters.report.capitalize()} — {product}**")
    st.caption(
        f"Source: {source} {filters.report.capitalize()} {settings.BASIS_LABELS.get(filters.basis, filters.basis)}"
        f"  |  {table.index.min():%d %b %Y} – {table.index.max():%d %b %Y}"
        f"  |  All positions in {'% of open interest' if pct else 'contracts'}"
        + ("  |  Δ = week-on-week change" if changes else "")
    )
    st.markdown(tables.history_html(table, pct), unsafe_allow_html=True)

    export = table.copy()
    export.columns = [" ".join(part for part in column) for column in export.columns]
    export.index.name = "Report date"
    st.download_button(
        "Download this table as CSV",
        data=export.to_csv().encode("utf-8"),
        file_name=f"cot_{product.lower().replace(' ', '_')}_{table.index.max():%Y%m%d}.csv",
        mime="text/csv",
    )


# --------------------------------------------------------------------------
# 4. Breakdown
# --------------------------------------------------------------------------
def breakdown_tab(frame: pd.DataFrame, filters: Filters) -> None:
    dates = _date_options(frame)
    if not dates:
        return empty_state("No history loaded.")

    top = st.columns([2, 3])
    state.ensure_option("breakdown_date", dates)
    as_of = top[0].selectbox(
        "Report date", options=dates, format_func=_fmt_date, key="breakdown_date"
    )
    products = sorted(frame["product"].unique())
    state.ensure_option("breakdown_product", products)
    product = top[1].selectbox("Product", options=products, key="breakdown_product")

    snapshot = frame[frame["report_date"].eq(as_of) & frame["product"].eq(product)].copy()
    if snapshot.empty:
        return empty_state("No data for that product on that date.")

    snapshot["category_label"] = snapshot["category"].map(category_labels(filters.report))
    snapshot = snapshot[snapshot["category"].isin(filters.categories)]
    if snapshot.empty:
        return empty_state(
            "This report has no data for the selected trader categories."
        )

    present = [c for c in filters.categories if c in set(snapshot["category"])]
    headline_category = present[0]
    open_interest = snapshot["open_interest"].max()
    head = st.columns(3)
    head[0].metric("Open interest", theme.fmt_int(open_interest))
    total_net = snapshot.loc[snapshot["category"].eq(headline_category), "net"].sum()
    head[1].metric(
        f"{category_labels(filters.report).get(headline_category, '')} net",
        theme.fmt_int(total_net),
    )
    head[2].metric(
        "Net % of OI",
        theme.fmt_pct(total_net / open_interest * 100 if open_interest else float("nan")),
    )

    figure = go.Figure()
    figure.add_bar(
        y=snapshot["category_label"],
        x=snapshot["long"],
        name="Long",
        orientation="h",
        marker_color=theme.LONG,
    )
    figure.add_bar(
        y=snapshot["category_label"],
        x=-snapshot["short"],
        name="Short",
        orientation="h",
        marker_color=theme.SHORT,
    )
    figure.update_layout(barmode="relative", title=f"{product} — {_fmt_date(as_of)}")
    figure.update_xaxes(title="Contracts (short shown negative)")
    st.plotly_chart(theme.layout(figure, height=380), **theme.wide())

    detail = cot.concentration(snapshot)
    detail["category"] = detail["category"].map(category_labels(filters.report))
    detail = detail.drop(columns=["product"]).rename(
        columns={
            "category": "Category",
            "long": "Long",
            "short": "Short",
            "spread": "Spread",
            "net": "Net",
            "net_pct_oi": "Net % of OI",
            "long_short_ratio": "Long / short",
            "open_interest": "Open interest",
        }
    )
    st.dataframe(
        detail,
        **theme.wide(),
        hide_index=True,
        column_config={
            "Net % of OI": st.column_config.NumberColumn(format="%.1f%%"),
            "Long / short": st.column_config.NumberColumn(format="%.2f"),
        },
    )


# --------------------------------------------------------------------------
# 5. Data
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Storage (EIA weekly stocks)
# --------------------------------------------------------------------------
def _storage_setup_help() -> None:
    st.info(
        "Storage needs a free EIA API key. Get one at eia.gov/opendata, then add "
        '`EIA_API_KEY = "your-key"` to `.streamlit/secrets.toml` (or the Secrets box on '
        "Community Cloud) and restart.",
        icon="🔑",
    )


def _seasonal_figure(name: str, stats: pd.DataFrame, unit: str) -> go.Figure:
    last_year = int(stats["year"].iloc[-1])
    this = stats[stats["year"].eq(last_year)]
    prior = stats[stats["year"].eq(last_year - 1)]
    band = stats[stats["year"].eq(last_year)].dropna(subset=["min5"])
    fig = go.Figure()
    if not band.empty:
        fig.add_scatter(x=band["week"], y=band["max5"], mode="lines", line=dict(width=0),
                        hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=band["week"], y=band["min5"], mode="lines", line=dict(width=0),
                        fill="tonexty", fillcolor="rgba(18,80,111,0.14)", name="5-yr range", hoverinfo="skip")
        fig.add_scatter(x=band["week"], y=band["avg5"], mode="lines", name="5-yr average",
                        line=dict(color=theme.MUTED, dash="dash", width=1.5))
    fig.add_scatter(x=prior["week"], y=prior["value"], mode="lines", name=str(last_year - 1),
                    line=dict(color="#c2571a", width=1.5))
    fig.add_scatter(x=this["week"], y=this["value"], mode="lines", name=str(last_year),
                    line=dict(color=theme.LONG, width=3))
    fig.update_xaxes(title="ISO week")
    fig.update_yaxes(title=f"{name} ({eia.UNIT_LABEL.get(unit, unit)})")
    return theme.layout(fig, height=430)


def _overlay_figure(name: str, unit: str, merged: pd.DataFrame, product: str, category: str) -> go.Figure:
    from plotly.subplots import make_subplots

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=merged.index, y=merged["stocks"], name=f"{name} stocks", mode="lines",
                    line=dict(color=theme.LONG, width=2.5), secondary_y=False)
    fig.add_scatter(x=merged.index, y=merged["net"], name=f"{product}: {category} net", mode="lines",
                    line=dict(color="#c2571a", width=2), secondary_y=True)
    fig.update_yaxes(title_text=f"{name} ({eia.UNIT_LABEL.get(unit, unit)})", secondary_y=False)
    fig.update_yaxes(title_text="Net contracts", secondary_y=True, showgrid=False)
    return theme.layout(fig, height=430)


def _stocks_label(frame: pd.DataFrame) -> str:
    return f"EIA week ending {frame['Week ending'].max():%d %b %Y}"


def storage_summary(as_of, baseline) -> None:
    """EIA stocks for the two dates being compared, and the change, under the CFTC tables.

    Each CFTC date (a Tuesday) is paired with the newest EIA week ending on or before it.
    When stocks cannot be loaded it says why in one line instead of staying silent.
    """
    st.markdown(
        "<div class='sec-gap'></div><hr class='sec-rule'><div class='sec-title'>US stocks (EIA)</div>", unsafe_allow_html=True
    )
    try:
        data = services.load_storage()
    except eia.EiaError as error:
        st.caption(f"📦 Not shown: {error}")
        return
    units = {s.key: s.unit for s in eia.SERIES}
    current = storage_stats.as_of_table(data, units, as_of)
    if current.empty:
        st.caption("📦 No EIA reading on or before this date.")
        return
    st.markdown(f"**{_stocks_label(current)}**, mbbls (gas in Bcf)")
    earlier = storage_stats.as_of_table(data, units, baseline) if baseline is not None else pd.DataFrame()
    scale = tables.stock_limits(current, earlier)  # one scale across both date tables
    st.markdown(tables.stocks_html(current, limits=scale), unsafe_allow_html=True)
    if earlier.empty:
        return
    st.markdown(f"**{_stocks_label(earlier)}**, mbbls (gas in Bcf)")
    st.markdown(tables.stocks_html(earlier, limits=scale), unsafe_allow_html=True)
    st.markdown(
        f"**Change** · EIA week ending {current['Week ending'].max():%d %b %Y} vs "
        f"{earlier['Week ending'].max():%d %b %Y}, mbbls (gas in Bcf)"
    )
    moves = storage_stats.difference(current, earlier)
    st.markdown(
        tables.stocks_html(moves, columns=tables.STOCK_CHANGE_COLUMNS, limits=tables.stock_limits(moves)),
        unsafe_allow_html=True,
    )


def storage_tab(frame: pd.DataFrame, filters: Filters) -> None:
    """EIA weekly US stocks: latest readings, the seasonal picture, and positioning beside them."""
    try:
        with st.spinner("Loading EIA stocks…"):
            data = services.load_storage()
    except eia.EiaError as error:
        if not services.eia_available():
            return _storage_setup_help()
        st.error(str(error))
        return None

    units = {s.key: s.unit for s in eia.SERIES}
    names = [s.key for s in eia.SERIES if s.key in set(data["series"])]
    if not names:
        return empty_state("EIA returned none of the expected series.")

    table = storage_stats.latest_table(data, units)
    newest = table["Week ending"].max()
    st.caption(f"Latest EIA reading: week ending {newest:%d %b %Y}. Petroleum in mbbls (million barrels), gas in Bcf.")
    shown = table.assign(**{"Week ending": table["Week ending"].dt.strftime("%d %b %Y"),
                            "Unit": table["Unit"].map(eia.UNIT_LABEL)})
    signed = lambda fmt: st.column_config.NumberColumn(format=fmt)  # noqa: E731
    st.dataframe(
        shown, hide_index=True, **theme.wide(),
        column_config={
            "Level": signed("%.1f"), "Week change": signed("%+.1f"), "vs 5-yr avg": signed("%+.1f"),
            "vs 5-yr avg %": signed("%+.1f%%"), "Year on year": signed("%+.1f"),
        },
    )

    controls = st.columns([2, 2, 2, 2])
    state.ensure_option("storage_series", names)
    name = controls[0].selectbox("Series", names, key="storage_series")
    view = controls[1].radio("View", ["Seasonal", "With positioning"], horizontal=True, key="storage_view")
    series = data[data["series"].eq(name)].set_index("period")["value"]
    unit = units[name]

    if view == "Seasonal":
        st.plotly_chart(_seasonal_figure(name, storage_stats.seasonal(series), unit), **theme.wide())
        st.caption("Shaded band: low to high of the same week over the previous five years.")
        return None

    products = sorted(frame["product"].unique())
    labels = category_labels(filters.report)
    present = [c for c in labels if c in set(frame["category"])]
    if not products or not present:
        return empty_state("Pick a product and trader category in the sidebar first.")
    state.ensure_option("storage_product", products)
    state.ensure_option("storage_category", present)
    product = controls[2].selectbox("Product", products, key="storage_product")
    category = controls[3].selectbox("Trader category", present, format_func=labels.get, key="storage_category")
    positions = frame[frame["product"].eq(product) & frame["category"].eq(category)]
    merged = storage_stats.positioning_overlay(series, positions)
    if merged.empty:
        return empty_state("No overlapping weeks between the stocks and this positioning series.")
    st.plotly_chart(_overlay_figure(name, unit, merged, product, labels[category]), **theme.wide())
    st.caption("Each stock reading is paired with the latest CFTC positions on or before it (net, in contracts).")
    return None


def coverage_panel(catalog: pd.DataFrame) -> None:
    """Every contract found, where it came from, and which group it landed in."""
    if catalog is None or catalog.empty:
        return
    from_subgroup = int(catalog["source"].astype(str).str.startswith("CFTC petroleum").sum())
    swept = int(catalog["source"].astype(str).str.startswith("Oil-name").sum())
    with st.expander(f"Contract coverage · {len(catalog)} contracts found"):
        st.caption(
            f"{from_subgroup} are in the CFTC's petroleum subgroup and {swept} are "
            "oil-named contracts filed under another subgroup; the rest come from "
            "ICE or demo data. A contract is kept if it reported in the last "
            f"{settings.CONTRACT_LOOKBACK_WEEKS} weeks. If a contract you expect "
            "isn't listed, the CFTC does not file it under petroleum or an oil-like "
            "name in this report. To move a contract between groups, add its code to "
            "GROUP_OVERRIDES in config/settings.py."
        )
        order = {g: i for i, g in enumerate(settings.GROUP_ORDER)}
        table = catalog.assign(_order=catalog["group"].map(order).fillna(len(order)))
        table = table.sort_values(["_order", "open_interest"], ascending=[True, False])
        table = table[
            ["product", "group", "exchange", "contract_code", "source", "last_report", "open_interest"]
        ].rename(
            columns={
                "product": "Product",
                "group": "Group",
                "exchange": "Exchange",
                "contract_code": "Contract code",
                "source": "Found via",
                "last_report": "Last report",
                "open_interest": "Open interest",
            }
        )
        st.dataframe(
            table,
            hide_index=True,
            **theme.wide(),
            column_config={
                "Last report": st.column_config.DateColumn(format="DD MMM YYYY"),
                "Open interest": st.column_config.NumberColumn(format="%d"),
            },
        )


def data_tab(frame: pd.DataFrame, filters: Filters, catalog: pd.DataFrame | None = None) -> None:
    coverage_panel(catalog)
    view = _value_frame(frame, filters).copy()
    if view.empty:
        return empty_state("Nothing loaded.")

    view["category"] = view["category"].map(category_labels(filters.report))
    columns = [
        "report_date",
        "product",
        "group",
        "contract_code",
        "category",
        "long",
        "short",
        "spread",
        "net",
        "net_pct_oi",
        "open_interest",
        "net_chg_1w",
        "net_chg_4w",
        "net_chg_13w",
        "net_chg_52w",
        "net_z",
        "cot_index",
    ]
    view = view[[c for c in columns if c in view.columns]].sort_values(
        ["report_date", "product", "category"], ascending=[False, True, True]
    )

    st.caption(f"{len(view):,} rows · {view['report_date'].min():%d %b %Y} to "
               f"{view['report_date'].max():%d %b %Y}")
    st.dataframe(view, hide_index=True, height=520, **theme.wide())
    st.download_button(
        "Download CSV",
        data=view.to_csv(index=False).encode("utf-8"),
        file_name=f"cot_petroleum_{pd.Timestamp.today():%Y%m%d}.csv",
        mime="text/csv",
    )
