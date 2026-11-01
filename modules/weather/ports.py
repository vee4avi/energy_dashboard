"""The ports on the weather map and the watch thresholds. Edit either here.

Coordinates sit just offshore of each port (the anchorage or the approach), so the
marine model reads sea, not land.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    region: str
    name: str
    lat: float
    lon: float


PORTS: tuple[Port, ...] = (
    Port("US Gulf Coast", "Houston / Galveston", 29.30, -94.65),
    Port("US Gulf Coast", "Corpus Christi", 27.80, -97.00),
    Port("US East Coast", "New York Harbor", 40.45, -73.85),
    Port("ARA", "Rotterdam", 51.98, 3.95),
    Port("ARA", "Antwerp (Scheldt mouth)", 51.45, 3.45),
    Port("ARA", "Amsterdam (IJmuiden)", 52.47, 4.45),
    Port("Middle East", "Fujairah", 25.15, 56.45),
    Port("Middle East", "Strait of Hormuz", 26.55, 56.30),
    Port("Middle East", "Ras Tanura", 26.70, 50.25),
    Port("China", "Qingdao", 35.95, 120.40),
    Port("China", "Ningbo-Zhoushan", 29.85, 122.20),
    Port("India", "Sikka / Vadinar", 22.55, 69.65),
    Port("India", "Mumbai", 18.90, 72.75),
    Port("India", "Chennai", 13.10, 80.35),
    Port("India", "Paradip", 20.25, 86.75),
    Port("South Korea", "Ulsan", 35.45, 129.45),
    Port("South Korea", "Yeosu", 34.65, 127.80),
    Port("South Korea", "Daesan", 37.00, 126.25),
    Port("Japan", "Tokyo Bay (Chiba)", 35.25, 139.75),
    Port("Japan", "Osaka Bay", 34.50, 135.20),
    Port("Japan", "Mizushima", 34.40, 133.80),
    Port("Japan", "Kiire", 31.35, 130.60),
)
REGIONS = tuple(dict.fromkeys(p.region for p in PORTS))

# Watch thresholds: starting points, not official limits. A port is "Now" when a reading
# crosses one at the current hour, "Watch" when one is crossed within LOOKAHEAD_HOURS.
THRESHOLDS = {
    "wave_height": 2.5,  # significant wave height, metres (above = breach)
    "wind_speed": 25.0,  # sustained wind, knots (above = breach)
    "visibility": 1.0,  # nautical miles (below = breach)
}
LOOKAHEAD_HOURS = 48
