"""Synthetic forecasts for COT_DEMO=1 (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.weather.ports import PORTS


def forecast(now: pd.Timestamp | None = None) -> pd.DataFrame:
    now = (now or pd.Timestamp.now(tz="UTC")).floor("h")
    times = pd.date_range(now - pd.Timedelta(hours=6), periods=6 + 96, freq="h")
    rng = np.random.default_rng(3)
    rows = []
    for i, port in enumerate(PORTS):
        base_wave = 0.6 + (i % 5) * 0.45
        base_wind = 8 + (i % 6) * 3.5
        swing = np.sin(np.linspace(0, 3 * np.pi, len(times)) + i)
        wave = np.clip(base_wave + 0.9 * swing + rng.normal(0, 0.1, len(times)), 0.1, None)
        wind = np.clip(base_wind + 9 * swing + rng.normal(0, 1.5, len(times)), 0, None)
        vis = np.where((i % 7 == 0) & (np.arange(len(times)) % 24 < 4), 0.6, 8.0 + rng.normal(0, .5, len(times)))
        for t, w, k, v in zip(times, wave, wind, vis):
            rows.append((port.name, t, w, w * 0.6, 6 + w, 0.3 * np.sin(t.hour / 12.4 * 2 * np.pi), k, k * 1.3, v))
    return pd.DataFrame(rows, columns=["port", "time", "wave_height", "swell_wave_height", "wave_period",
                                       "sea_level", "wind_speed", "wind_gusts", "visibility"])
