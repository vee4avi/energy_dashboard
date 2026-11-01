"""Turn the hourly forecast into a status per port. No Streamlit."""

from __future__ import annotations

import pandas as pd

from modules.weather.ports import LOOKAHEAD_HOURS, PORTS, THRESHOLDS

CLEAR, WATCH, NOW = "Clear", "Watch", "Now"
LABELS = {"wave_height": "waves", "wind_speed": "wind", "visibility": "visibility"}


def breaches(row: pd.Series) -> list[str]:
    """Which thresholds one hourly reading crosses."""
    out = []
    if pd.notna(row.get("wave_height")) and row["wave_height"] > THRESHOLDS["wave_height"]:
        out.append("wave_height")
    if pd.notna(row.get("wind_speed")) and row["wind_speed"] > THRESHOLDS["wind_speed"]:
        out.append("wind_speed")
    if pd.notna(row.get("visibility")) and row["visibility"] < THRESHOLDS["visibility"]:
        out.append("visibility")
    return out


def summary(forecast: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """One row per port: current readings, status, and the first breach ahead."""
    now = pd.Timestamp(now).tz_convert("UTC") if pd.Timestamp(now).tzinfo else pd.Timestamp(now, tz="UTC")
    horizon = now + pd.Timedelta(hours=LOOKAHEAD_HOURS)
    rows = []
    for port in PORTS:
        mine = forecast[forecast["port"].eq(port.name)]
        if mine.empty:
            rows.append({"port": port.name, "region": port.region, "lat": port.lat, "lon": port.lon,
                         "status": "No data", "reason": ""})
            continue
        current = mine.iloc[(mine["time"] - now).abs().argmin()]
        ahead = mine[(mine["time"] > current["time"]) & (mine["time"] <= horizon)]
        now_hits = breaches(current)
        later = [(r["time"], breaches(r)) for _, r in ahead.iterrows()]
        later = [(t, b) for t, b in later if b]
        if now_hits:
            status, reason = NOW, ", ".join(LABELS[b] for b in now_hits)
        elif later:
            first_time, first_hits = later[0]
            status = WATCH
            local = first_time.tz_convert("Asia/Singapore")
            reason = f"{', '.join(LABELS[b] for b in first_hits)} from {local:%a %d %b %H:%M} SGT"
        else:
            status, reason = CLEAR, ""
        window = mine[(mine["time"] >= current["time"]) & (mine["time"] <= horizon)]
        rows.append({
            "port": port.name, "region": port.region, "lat": port.lat, "lon": port.lon,
            "status": status, "reason": reason, "as_of": current["time"],
            "wave_height": current["wave_height"], "swell_wave_height": current["swell_wave_height"],
            "wave_period": current["wave_period"], "wind_speed": current["wind_speed"],
            "wind_gusts": current["wind_gusts"], "visibility": current["visibility"],
            "max_wave_48h": window["wave_height"].max(), "max_wind_48h": window["wind_speed"].max(),
            "min_vis_48h": window["visibility"].min(),
        })
    return pd.DataFrame(rows)
