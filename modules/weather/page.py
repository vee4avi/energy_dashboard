"""Weather and sea state for key shipping regions: placeholder until it is built."""

from __future__ import annotations

from shared import ui


def render() -> None:
    ui.coming_soon(
        "Weather & sea state",
        "🌊",
        "Wind, waves, swell and storms in the coastal regions that matter for physical cargo.",
        planned=[
            "A map of the regions you pick, each lit up when a reading crosses your threshold",
            "Forecast wind, wave and swell height for the next few days",
            "Storm and tropical-cyclone alerts near loading ports",
        ],
        sources=["Regions and thresholds to be chosen", "A free marine-weather data source to be settled"],
    )
