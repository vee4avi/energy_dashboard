"""Marine and weather forecasts for the ports, from Open-Meteo. No Streamlit.

Two free endpoints, one request each for every port at once:
  https://marine-api.open-meteo.com/v1/marine   waves, swell, sea level
  https://api.open-meteo.com/v1/forecast         wind, gusts, visibility
Free for non-commercial use; Open-Meteo asks to be credited (the page does).
"""

from __future__ import annotations

import pandas as pd
import requests

from modules.weather.ports import PORTS, Port

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_VARS = ("wave_height", "swell_wave_height", "wave_period", "sea_level_height_msl")
WEATHER_VARS = ("wind_speed_10m", "wind_gusts_10m", "visibility")
METRES_PER_NM = 1852.0
TIMEOUT = 30


class WeatherError(RuntimeError):
    """Safe to show."""


def _get(url: str, params: dict) -> list[dict]:
    try:
        reply = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise WeatherError(f"Could not reach Open-Meteo ({type(error).__name__}).") from None
    if reply.status_code != 200:
        try:
            reason = reply.json().get("reason", "")
        except ValueError:
            reason = ""
        raise WeatherError(f"Open-Meteo answered HTTP {reply.status_code}. {reason}".strip())
    payload = reply.json()
    return payload if isinstance(payload, list) else [payload]  # one location -> one object


def parse(payloads: list[dict], ports: tuple[Port, ...], variables: tuple[str, ...]) -> pd.DataFrame:
    """Open-Meteo's per-location objects -> rows of (port, time, variable values)."""
    frames = []
    for port, payload in zip(ports, payloads):
        hourly = (payload or {}).get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            continue
        frame = pd.DataFrame({"time": pd.to_datetime(times, utc=True)})
        for name in variables:
            values = hourly.get(name)
            frame[name] = pd.to_numeric(pd.Series(values if values is not None else [None] * len(times)),
                                        errors="coerce")
        frame.insert(0, "port", port.name)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch(ports: tuple[Port, ...] = PORTS, days: int = 4) -> pd.DataFrame:
    """Hourly forecast for every port: waves (m), wind (kn), visibility (nm), sea level (m)."""
    common = {
        "latitude": ",".join(f"{p.lat:.3f}" for p in ports),
        "longitude": ",".join(f"{p.lon:.3f}" for p in ports),
        "timezone": "UTC",
        "forecast_days": days,
        "past_hours": 6,
    }
    marine = parse(_get(MARINE_URL, {**common, "hourly": ",".join(MARINE_VARS)}), ports, MARINE_VARS)
    weather = parse(
        _get(WEATHER_URL, {**common, "hourly": ",".join(WEATHER_VARS), "wind_speed_unit": "kn"}),
        ports, WEATHER_VARS,
    )
    if weather.empty and marine.empty:
        raise WeatherError("Open-Meteo returned no forecast.")
    frame = weather.merge(marine, on=["port", "time"], how="outer") if not marine.empty else weather
    return tidy(frame)


def tidy(frame: pd.DataFrame) -> pd.DataFrame:
    """Friendlier column names and units."""
    out = frame.rename(columns={
        "wind_speed_10m": "wind_speed", "wind_gusts_10m": "wind_gusts", "sea_level_height_msl": "sea_level",
    })
    if "visibility" in out:
        out["visibility"] = out["visibility"] / METRES_PER_NM
    for column in ("wave_height", "swell_wave_height", "wave_period", "sea_level", "wind_speed", "wind_gusts", "visibility"):
        if column not in out:
            out[column] = float("nan")
    return out.sort_values(["port", "time"]).reset_index(drop=True)
