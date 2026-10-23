"""Distance and travel time (AGENT §4)."""

import math
from typing import Protocol

from rakt import config

EARTH_RADIUS_KM = 6371


class Located(Protocol):
    lat: float
    lon: float


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def km(a: Located, b: Located) -> float:
    return haversine_km((a.lat, a.lon), (b.lat, b.lon))


def travel_min(a: Located, b: Located) -> float:
    return km(a, b) * config.ROAD_FACTOR / config.CITY_SPEED_KMPH * 60
