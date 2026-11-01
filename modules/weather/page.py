"""Weather & sea state at the ports that matter for physical cargo: a clickable map."""

from __future__ import annotations

import html
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.weather import analysis, demo, sources
from modules.weather.ports import LOOKAHEAD_HOURS, THRESHOLDS
from shared import theme

DEMO = os.getenv("COT_DEMO", "").strip().lower() in {"1", "true", "yes"}
COLOURS = {analysis.CLEAR: "#4f7a37", analysis.WATCH: "#d39b22", analysis.NOW: "#b8322a", "No data": "#9aa092"}
SGT = "Asia/Singapore"


@st.cache_data(ttl=30 * 60, show_spinner=False)
def _load() -> pd.DataFrame:
    return demo.forecast() if DEMO else sources.fetch()


# The basemap: Carto's free vector styles, drawn by MapLibre in the browser (no token).
# "carto-darkmatter" gives the dark, Kpler-like look; "carto-positron" is the light version.
MAP_STYLE = "carto-darkmatter"  # or "classic": the plain outline map, which needs no map tiles
MAP_CENTER = {"lat": 27.0, "lon": 40.0}
MAP_ZOOM = 1.25


def _hover(part: pd.DataFrame, status: str) -> list[str]:
    return [
        f"<b>{html.escape(r.port)}</b><br>{r.region}<br>{status}"
        + (f" — {html.escape(r.reason)}" if r.reason else "")
        + (f"<br>waves {r.wave_height:.1f} m · wind {r.wind_speed:.0f} kn · vis {r.visibility:.1f} nm"
           if pd.notna(getattr(r, "wave_height", None)) or pd.notna(getattr(r, "wind_speed", None)) else "")
        for r in part.itertuples()
    ]


def _classic_map(table: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for status, colour in COLOURS.items():
        part = table[table["status"].eq(status)]
        if not part.empty:
            fig.add_trace(go.Scattergeo(
                lon=part["lon"], lat=part["lat"], mode="markers", name=status, customdata=part["port"],
                text=_hover(part, status), hovertemplate="%{text}<extra></extra>",
                marker=dict(size=13, color=colour, line=dict(width=1.5, color="#1b1f18")),
            ))
    fig.update_geos(projection_type="mercator", showcountries=True, countrycolor="#b9bfae", showland=True,
                    landcolor="#e9ecdf", showocean=True, oceancolor="#dde8ee", coastlinecolor="#8c9480",
                    lataxis_range=[-2, 62], lonaxis_range=[-102, 148])
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="white",
                      legend=dict(orientation="h", y=1.02, x=0, title=""), dragmode="pan")
    return fig


def _map(table: pd.DataFrame) -> go.Figure:
    """Ports on a vector basemap: a soft halo under each marker, coloured by status."""
    if MAP_STYLE == "classic":
        return _classic_map(table)
    fig = go.Figure()
    for status, colour in COLOURS.items():
        part = table[table["status"].eq(status)]
        if part.empty:
            continue
        hover = _hover(part, status)
        fig.add_trace(go.Scattermap(  # halo; clicking it picks the port too
            lon=part["lon"], lat=part["lat"], mode="markers", hoverinfo="skip", showlegend=False,
            customdata=part["port"],
            marker=dict(size=26, color=colour, opacity=0.22),
        ))
        fig.add_trace(go.Scattermap(
            lon=part["lon"], lat=part["lat"], mode="markers", name=status,
            customdata=part["port"], text=hover, hovertemplate="%{text}<extra></extra>",
            marker=dict(size=11, color=colour, opacity=0.95),
        ))
    fig.update_layout(
        map=dict(style=MAP_STYLE, center=MAP_CENTER, zoom=MAP_ZOOM),
        height=470, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="#0e1116",
        legend=dict(orientation="h", y=0.02, x=0.01, title="", bgcolor="rgba(14,17,22,.75)",
                    font=dict(color="#e7eadf", size=12)),
        hoverlabel=dict(bgcolor="#1b2027", bordercolor="#3a4250", font=dict(color="#f2f4ee", size=12)),
    )
    return fig


def _map_config() -> dict:
    return {"scrollZoom": True, "displayModeBar": False}


def _clicked_port(event) -> str | None:
    try:
        points = event.selection.points  # type: ignore[union-attr]
    except AttributeError:
        return None
    if not points:
        return None
    first = points[0]
    value = first.get("customdata") if isinstance(first, dict) else getattr(first, "customdata", None)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return value


def _detail(name: str, row: pd.Series, forecast: pd.DataFrame) -> None:
    st.markdown(f"<div class='cal-title'>{html.escape(name)}</div>", unsafe_allow_html=True)
    status = row["status"]
    colour = COLOURS.get(status, "#555")
    st.markdown(
        f"<div style='font-weight:700;color:{colour};margin:-.2rem 0 .6rem 0'>{status}"
        + (f" — {html.escape(row['reason'])}" if row.get("reason") else "") + "</div>",
        unsafe_allow_html=True,
    )
    if status == "No data":
        st.caption("No forecast came back for this point.")
        return
    a, b, c = st.columns(3)
    a.metric("Waves", f"{row['wave_height']:.1f} m", f"swell {row['swell_wave_height']:.1f} m", delta_color="off")
    b.metric("Wind", f"{row['wind_speed']:.0f} kn", f"gusts {row['wind_gusts']:.0f} kn", delta_color="off")
    c.metric("Visibility", f"{row['visibility']:.1f} nm", f"period {row['wave_period']:.0f} s", delta_color="off")

    mine = forecast[forecast["port"].eq(name)]
    mine = mine[mine["time"] >= row["as_of"]].head(LOOKAHEAD_HOURS + 24)
    times = mine["time"].dt.tz_convert(SGT)
    from plotly.subplots import make_subplots

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=times, y=mine["wave_height"], name="Waves (m)", line=dict(color="#3e6e8e", width=2.5))
    fig.add_scatter(x=times, y=mine["wind_speed"], name="Wind (kn)", line=dict(color="#6f7d4a", width=2),
                    secondary_y=True)
    fig.add_hline(y=THRESHOLDS["wave_height"], line=dict(color="#3e6e8e", dash="dot", width=1))
    fig.add_hline(y=THRESHOLDS["wind_speed"], line=dict(color="#6f7d4a", dash="dot", width=1), secondary_y=True)
    fig.update_yaxes(title_text="Waves (m)", secondary_y=False, rangemode="tozero")
    fig.update_yaxes(title_text="Wind (kn)", secondary_y=True, showgrid=False, rangemode="tozero",
                     tickformat=".0f", tickmode="auto", nticks=6)
    theme.layout(fig, height=300)
    st.plotly_chart(fig, **theme.wide())
    st.caption("Next three days, Singapore time. Dotted lines are the watch thresholds.")


def _table(table: pd.DataFrame) -> str:
    order = {analysis.NOW: 0, analysis.WATCH: 1, analysis.CLEAR: 2, "No data": 3}
    table = table.assign(_o=table["status"].map(order)).sort_values(["_o", "region", "port"])
    head = "".join(f"<th>{h}</th>" for h in (
        "Port", "Region", "Status", "Waves (m)", "Wind (kn)", "Gusts (kn)", "Visibility (nm)",
        f"Max waves {LOOKAHEAD_HOURS}h", f"Max wind {LOOKAHEAD_HOURS}h", "Why"))
    def num(value, fmt):
        return "" if pd.isna(value) else fmt.format(value)
    rows = []
    for r in table.itertuples():
        colour = COLOURS.get(r.status, "#555")
        rows.append(
            "<tr>" + f"<td>{html.escape(r.port)}</td><td>{html.escape(r.region)}</td>"
            f"<td style='color:{colour};font-weight:700'>{r.status}</td>"
            f"<td>{num(getattr(r, 'wave_height', None), '{:.1f}')}</td>"
            f"<td>{num(getattr(r, 'wind_speed', None), '{:.0f}')}</td>"
            f"<td>{num(getattr(r, 'wind_gusts', None), '{:.0f}')}</td>"
            f"<td>{num(getattr(r, 'visibility', None), '{:.1f}')}</td>"
            f"<td>{num(getattr(r, 'max_wave_48h', None), '{:.1f}')}</td>"
            f"<td>{num(getattr(r, 'max_wind_48h', None), '{:.0f}')}</td>"
            f"<td>{html.escape(r.reason or '')}</td></tr>"
        )
    return (f'<div class="cal-wrap" style="max-height:640px"><table class="cal"><thead><tr>{head}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>")


def render() -> None:
    st.markdown("<div class='cal-title' style='font-size:26px'>Weather &amp; sea state</div>", unsafe_allow_html=True)
    st.caption(
        f"Watch: waves over {THRESHOLDS['wave_height']:g} m, wind over {THRESHOLDS['wind_speed']:g} kn or "
        f"visibility under {THRESHOLDS['visibility']:g} nm, now (red) or within {LOOKAHEAD_HOURS}h (amber). "
        "Click a port for its forecast (scroll to zoom, drag to pan). Weather data by Open-Meteo.com; "
        "map © OpenStreetMap contributors © CARTO."
    )
    try:
        with st.spinner("Loading forecasts…"):
            forecast = _load()
    except sources.WeatherError as error:
        st.error(str(error))
        return
    table = analysis.summary(forecast, pd.Timestamp.now(tz="UTC"))
    names = list(table["port"])

    left, right = st.columns([3, 2], gap="large")
    with left:
        event = st.plotly_chart(
            _map(table), key="weather_map", on_select="rerun", selection_mode="points",
            config=_map_config(), **theme.wide(),
        )
    clicked = _clicked_port(event)
    if clicked and clicked != st.session_state.get("_weather_last_click"):
        st.session_state["_weather_last_click"] = clicked
        st.session_state["weather_port"] = clicked
    if st.session_state.get("weather_port") not in names:
        first_alert = table[table["status"].isin([analysis.NOW, analysis.WATCH])]
        st.session_state["weather_port"] = first_alert["port"].iloc[0] if not first_alert.empty else names[0]
    with right:
        name = st.selectbox("Port", names, key="weather_port", label_visibility="collapsed")
        _detail(name, table.set_index("port").loc[name], forecast)

    st.markdown("<div class='cal-title' style='margin-top:.6rem'>All ports</div>", unsafe_allow_html=True)
    st.markdown(_table(table), unsafe_allow_html=True)
    st.caption(
        "Points sit just offshore of each port. Forecast resolution is a few kilometres, so treat this as a "
        "regional picture, not a berth-level one. Thresholds live in modules/weather/ports.py."
    )
