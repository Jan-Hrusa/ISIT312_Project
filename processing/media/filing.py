"""Filing a photo to its project by where and when it was taken (Task 19 filing rules).

A photo with GPS belongs to a signed project when its position is within the project's radius of the site
centre and it was taken between construction start - 30 days and construction end + 30 days (UTC dates);
when several projects match, the nearest centre wins. Everything else is `UNASSIGNED`.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import NamedTuple

from common import config

EARTH_RADIUS_M = 6_371_000.0
WINDOW_DAYS = 30

RULE_GPS = "GPS"
RULE_NONE = "NONE"
RULE_FOLDER = "FOLDER"


class Site(NamedTuple):
    """A signed project's site and the dates a photo of it may carry."""

    project_code: str
    lat: float
    lon: float
    radius_m: float
    first_day: date  # construction start - WINDOW_DAYS
    last_day: date  # construction end + WINDOW_DAYS


class Filing(NamedTuple):
    project_code: str
    filing_rule: str
    distance_m: float | None  # to the chosen site, or to the nearest site when unassigned; None without GPS


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (Earth radius 6,371,000 m, as the Task 7 generator uses)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def site(
    project_code: str,
    lat: float,
    lon: float,
    radius_m: float,
    construction_start: date,
    construction_end: date,
) -> Site:
    window = timedelta(days=WINDOW_DAYS)
    return Site(
        project_code, lat, lon, float(radius_m), construction_start - window, construction_end + window
    )


def sites_from_projects(rows) -> list[Site]:
    """Sites of the signed projects among `rows` (anything with the `projects` columns as attributes).

    NOT_SIGNED offers and projects without construction dates have no site a photo could belong to.
    """
    return [
        site(r.project_code, r.lat, r.lon, r.radius_m, r.construction_start, r.construction_end)
        for r in rows
        if r.status != "NOT_SIGNED"
        and r.construction_start is not None
        and r.construction_end is not None
        and r.lat is not None
        and r.lon is not None
    ]


def file_photo(taken_at: datetime | None, lat: float | None, lon: float | None, sites: list[Site]) -> Filing:
    """The project a photo is filed to, the rule that filed it and its distance to that (or nearest) site."""
    if lat is None or lon is None:
        return Filing(config.UNASSIGNED, RULE_NONE, None)
    distances = [(haversine_m(lat, lon, s.lat, s.lon), s) for s in sites]
    if not distances:
        return Filing(config.UNASSIGNED, RULE_NONE, None)
    day = taken_at.date() if taken_at is not None else None
    matches = [
        (d, s)
        for d, s in distances
        if d <= s.radius_m and day is not None and s.first_day <= day <= s.last_day
    ]
    if matches:
        d, s = min(matches, key=lambda m: m[0])
        return Filing(s.project_code, RULE_GPS, d)
    return Filing(config.UNASSIGNED, RULE_NONE, min(d for d, _ in distances))


def nearest_project(lat: float, lon: float, sites: list[Site]) -> str | None:
    """The project whose site centre is nearest, for the detail of an UNASSIGNED_PHOTO issue."""
    if not sites:
        return None
    return min(sites, key=lambda s: haversine_m(lat, lon, s.lat, s.lon)).project_code
