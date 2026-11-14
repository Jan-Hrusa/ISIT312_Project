"""Small helpers shared by the media generator modules."""

import math
import os
from datetime import date, datetime, timedelta, timezone

EARTH_RADIUS_M = 6_371_000.0
METRES_PER_DEG_LAT = 111_320.0


def business_ts(day: date) -> float:
    """POSIX timestamp of 12:00 UTC on `day`."""
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).timestamp()


def set_business_mtime(path, day: date) -> None:
    """Contract rule: every file's mtime = 12:00 UTC of its business date."""
    ts = business_ts(day)
    os.utime(path, (ts, ts))


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def offset(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """The point `north_m` / `east_m` metres from (lat, lon), rounded to 6 decimals (about 0.1 m)."""
    new_lat = lat + north_m / METRES_PER_DEG_LAT
    new_lon = lon + east_m / (METRES_PER_DEG_LAT * math.cos(math.radians(lat)))
    return round(new_lat, 6), round(new_lon, 6)


def days(start: date, end: date) -> list[date]:
    """Every day from start to end, both included."""
    return [start + timedelta(n) for n in range((end - start).days + 1)]


def workdays(start: date, end: date) -> list[date]:
    """Monday to Friday from start to end, both included."""
    return [d for d in days(start, end) if d.weekday() < 5]
