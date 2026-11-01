"""Tests for the weather map (offline).

Run with:  python tests/test_weather.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["COT_DEMO"] = "1"

from modules.weather import analysis, sources  # noqa: E402
from modules.weather.ports import PORTS, THRESHOLDS  # noqa: E402


def _payload(values: dict, hours: int = 3) -> dict:
    times = [f"2026-11-01T{h:02d}:00" for h in range(hours)]
    return {"latitude": 1, "longitude": 2, "hourly": {"time": times, **values}}


def test_parse_and_tidy() -> None:
    ports = PORTS[:2]
    weather = sources.parse(
        [_payload({"wind_speed_10m": [10, 20, 30], "wind_gusts_10m": [15, 25, 35], "visibility": [1852, 926, None]}),
         _payload({"wind_speed_10m": [5, 5, 5], "wind_gusts_10m": [6, 6, 6], "visibility": [9260, 9260, 9260]})],
        ports, sources.WEATHER_VARS,
    )
    marine = sources.parse(
        [_payload({"wave_height": [1, 2, 3], "swell_wave_height": [1, 1, 1], "wave_period": [7, 7, 7],
                   "sea_level_height_msl": [0.1, 0.2, 0.3]}),
         {"hourly": {}}],  # a point on land: no marine data
        ports, sources.MARINE_VARS,
    )
    frame = sources.tidy(weather.merge(marine, on=["port", "time"], how="outer"))
    first = frame[frame["port"].eq(PORTS[0].name)]
    assert list(first["visibility"].round(2))[:2] == [1.0, 0.5], "metres become nautical miles"
    assert first["wave_height"].tolist() == [1, 2, 3] and first["wind_speed"].tolist() == [10, 20, 30]
    second = frame[frame["port"].eq(PORTS[1].name)]
    assert second["wave_height"].isna().all(), "no marine data is left blank, not an error"
    assert str(frame["time"].dt.tz) == "UTC"
    print("parse: ok")


def test_status() -> None:
    now = pd.Timestamp("2026-11-01T00:00", tz="UTC")
    times = pd.date_range(now, periods=60, freq="h")
    rows = []
    for port in PORTS:
        wave = [1.0] * 60
        wind = [10.0] * 60
        vis = [5.0] * 60
        if port is PORTS[0]:
            wave[0] = THRESHOLDS["wave_height"] + 0.5  # breach now
        if port is PORTS[1]:
            wind[10] = THRESHOLDS["wind_speed"] + 5  # breach later
        if port is PORTS[2]:
            vis[55] = 0.2  # beyond 48 h: does not count
        for t, a, b, c in zip(times, wave, wind, vis):
            rows.append((port.name, t, a, 0.5, 6, 0, b, b * 1.3, c))
    forecast = pd.DataFrame(rows, columns=["port", "time", "wave_height", "swell_wave_height", "wave_period",
                                           "sea_level", "wind_speed", "wind_gusts", "visibility"])
    table = analysis.summary(forecast, now).set_index("port")
    assert table.loc[PORTS[0].name, "status"] == analysis.NOW and table.loc[PORTS[0].name, "reason"] == "waves"
    assert table.loc[PORTS[1].name, "status"] == analysis.WATCH
    assert table.loc[PORTS[1].name, "reason"] == "wind from Sun 01 Nov 18:00 SGT", "times shown in Singapore time"
    assert table.loc[PORTS[2].name, "status"] == analysis.CLEAR, "a breach past the look-ahead is ignored"
    missing = analysis.summary(forecast[~forecast["port"].eq(PORTS[3].name)], now).set_index("port")
    assert missing.loc[PORTS[3].name, "status"] == "No data"
    print("status: ok")


def test_ports() -> None:
    names = [p.name for p in PORTS]
    assert len(names) == len(set(names))
    regions = {p.region for p in PORTS}
    assert {"US Gulf Coast", "ARA", "Middle East", "China", "India", "South Korea", "Japan"} <= regions
    assert all(-90 <= p.lat <= 90 and -180 <= p.lon <= 180 for p in PORTS)
    print("ports: ok")


def test_both_map_styles() -> None:
    from modules.weather import page

    now = pd.Timestamp.now(tz="UTC")
    from modules.weather import demo

    table = analysis.summary(demo.forecast(now), now)
    vector = page._map(table)
    assert vector.layout.map.style == "carto-darkmatter"
    clickable = [t for t in vector.data if t.hoverinfo != "skip"]
    assert sum(len(t.lat) for t in clickable) == len(PORTS), "every port once (halos aside)"
    saved = page.MAP_STYLE
    try:
        page.MAP_STYLE = "classic"
        classic = page._map(table)
        assert classic.data[0].type == "scattergeo"
    finally:
        page.MAP_STYLE = saved
    print("map styles: ok")


def test_page_runs_and_port_picker() -> None:
    from streamlit.testing.v1 import AppTest

    os.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "tests" / "weather_entry.py"), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    picker = at.selectbox(key="weather_port")
    assert len(picker.options) == len(PORTS)
    for name in (PORTS[0].name, PORTS[-1].name):
        picker.set_value(name).run()
        assert not at.exception, [e.value for e in at.exception]
    text = "\n".join(m.value for m in at.markdown)
    assert "All ports" in text and PORTS[-1].name in text
    print("weather page: ok")


if __name__ == "__main__":
    test_parse_and_tidy()
    test_status()
    test_ports()
    test_both_map_styles()
    test_page_runs_and_port_picker()
    print("\nall weather tests passed")
