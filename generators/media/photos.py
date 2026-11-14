"""Site photos: which photos exist (plan), the planted problems, and the JPEG bytes (render).

Each signed project gets FIRST_WEEK_PHOTOS photos spread over the workdays of its first construction week,
then WEEKLY_PHOTOS photos every following week, all on one workday of that week (the site manager's weekly
visit), until construction ends (Task 7; ~300-400 photos per completed project). Photos are taken in working
hours within 90% of the site radius (so rounding never pushes a photo out of its site); nothing after DATA_END
exists, so an ACTIVE project's photos stop there. Then 10% of all photos lose their GPS (NO_GPS) and 1% get a
position 2-5 km from their own site and outside every project's radius (WRONG_SITE).
"""

import io
import math
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from common import config
from common.projects import Project
from generators.media.util import distance_m, offset, workdays

FIRST_WEEK_PHOTOS = (100, 150)  # spread over the first construction week
WEEKLY_PHOTOS = (3, 8)  # every later week, on one workday
NO_GPS_SHARE = 0.10
WRONG_SITE_SHARE = 0.01
WRONG_SITE_M = (2_000.0, 5_000.0)  # distance from the photo's own site
WRONG_SITE_CLEARANCE_M = 100.0  # at least this far outside every project's radius
SITE_SHARE = 0.9  # photos fall within this share of the radius
WORK_HOURS_UTC = (6, 16)  # first and last+1 hour (08:00-18:00 Czech summer time)
WIDTH, HEIGHT, QUALITY = 320, 240, 70

DEVICES = (
    ("Samsung", "Galaxy A54"),
    ("Apple", "iPhone 13"),
    ("Xiaomi", "Redmi Note 12"),
    ("Google", "Pixel 7a"),
)


class PhotoSpec(NamedTuple):
    name: str
    taken_at: datetime  # UTC
    lat: float | None
    lon: float | None
    device: tuple[str, str]
    project_code: str  # the project the photo was taken for (truth, not in the file)
    planted: str | None  # None, NO_GPS or WRONG_SITE


def photo_name(taken_at: datetime, n: int) -> str:
    """IMG_<yyyyMMdd>_<HHmmss>_<nnnnn>.jpg; n counts the photos of one day, so names are globally unique."""
    return f"IMG_{taken_at:%Y%m%d_%H%M%S}_{n:05d}.jpg"


def photo_period(project: Project, data_end: date) -> tuple[date, date] | None:
    """First and last day photos can exist for (construction, cut at data_end); None if none can."""
    if not project.is_signed or project.construction_start is None or project.construction_end is None:
        return None
    if project.construction_start > data_end:
        return None
    return project.construction_start, min(project.construction_end, data_end)


def shoot_days(project: Project, rng) -> list[date]:
    """One date per photo over the project's whole construction (before any DATA_END cut): FIRST_WEEK_PHOTOS
    on random workdays of the first week, then WEEKLY_PHOTOS on one random workday of each later week."""
    start, end = project.construction_start, project.construction_end
    days = []
    first_week = workdays(start, min(start + timedelta(6), end))
    if first_week:
        days += [rng.choice(first_week) for _ in range(rng.randint(*FIRST_WEEK_PHOTOS))]
    week = start + timedelta(7)
    while week <= end:
        work = workdays(week, min(week + timedelta(6), end))
        if work:
            days += [rng.choice(work)] * rng.randint(*WEEKLY_PHOTOS)
        week += timedelta(7)
    return days


def plan(projects: list[Project], rng, data_end: date = config.DATA_END) -> list[PhotoSpec]:
    """Every photo of every signed project, with the planted problems, sorted by name."""
    raw = []  # [taken_at, project_code, lat, lon, device, planted]
    for p in projects:
        if photo_period(p, data_end) is None:
            continue
        for day in shoot_days(p, rng):
            if day > data_end:
                continue
            second = rng.randrange(WORK_HOURS_UTC[0] * 3600, WORK_HOURS_UTC[1] * 3600)
            taken = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(seconds=second)
            bearing = rng.uniform(0, 2 * math.pi)
            dist = p.radius_m * SITE_SHARE * math.sqrt(rng.random())  # uniform over the disc
            lat, lon = offset(p.lat, p.lon, dist * math.cos(bearing), dist * math.sin(bearing))
            raw.append([taken, p.project_code, lat, lon, rng.choice(DEVICES), None])

    _plant(raw, projects, rng)

    raw.sort(key=lambda r: (r[0], r[1]))
    per_day: dict[date, int] = {}
    specs = []
    for taken, code, lat, lon, device, planted in raw:
        n = per_day[taken.date()] = per_day.get(taken.date(), 0) + 1
        specs.append(PhotoSpec(photo_name(taken, n), taken, lat, lon, device, code, planted))
    return specs


def _plant(raw: list, projects: list[Project], rng) -> None:
    """NO_GPS on NO_GPS_SHARE of the photos, WRONG_SITE on WRONG_SITE_SHARE of the others (in place)."""
    if not raw:
        return
    by_code = {p.project_code: p for p in projects}
    order = list(range(len(raw)))
    rng.shuffle(order)
    n_no_gps = round(len(raw) * NO_GPS_SHARE)
    n_wrong = min(round(len(raw) * WRONG_SITE_SHARE), len(raw) - n_no_gps)
    for i in order[:n_no_gps]:
        raw[i][2] = raw[i][3] = None
        raw[i][5] = "NO_GPS"
    for i in order[n_no_gps : n_no_gps + n_wrong]:
        raw[i][2], raw[i][3] = wrong_site_position(by_code[raw[i][1]], projects, rng)
        raw[i][5] = "WRONG_SITE"


def wrong_site_position(own: Project, projects: list[Project], rng) -> tuple[float, float]:
    """A position WRONG_SITE_M from the own site and at least WRONG_SITE_CLEARANCE_M outside every project's
    radius, so photo filing can't place it on any site."""
    while True:
        bearing = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(*WRONG_SITE_M)
        lat, lon = offset(own.lat, own.lon, dist * math.cos(bearing), dist * math.sin(bearing))
        own_m = distance_m(lat, lon, own.lat, own.lon)
        if WRONG_SITE_M[0] <= own_m <= WRONG_SITE_M[1] and all(
            distance_m(lat, lon, p.lat, p.lon) >= p.radius_m + WRONG_SITE_CLEARANCE_M for p in projects
        ):
            return lat, lon


def nearest_site_m(lat: float, lon: float, projects: list[Project]) -> float:
    return min(distance_m(lat, lon, p.lat, p.lon) for p in projects)


def render(spec: PhotoSpec, rng) -> bytes:
    """A 320x240 JPEG (quality 70): sky, ground and panel rows in random tones, with the date and the
    file name drawn on it (no project code: filing must come from GPS and date)."""
    sky = (rng.randrange(120, 200), rng.randrange(160, 220), rng.randrange(200, 255))
    ground = (rng.randrange(90, 150), rng.randrange(80, 130), rng.randrange(40, 90))
    horizon = rng.randrange(70, 120)
    img = Image.new("RGB", (WIDTH, HEIGHT), sky)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, horizon, WIDTH, HEIGHT], fill=ground)
    for row in range(rng.randrange(2, 5)):
        y = horizon + 20 + row * 30
        x0 = rng.randrange(0, 60)
        shade = rng.randrange(20, 60)
        draw.polygon(
            [(x0, y + 18), (x0 + 30, y), (WIDTH - x0, y), (WIDTH - x0 - 30, y + 18)],
            fill=(shade, shade + 10, shade + 50),
        )
    font = ImageFont.load_default()
    draw.rectangle([0, 0, WIDTH, 30], fill=(0, 0, 0))
    draw.text((6, 3), f"{spec.taken_at:%Y-%m-%d %H:%M:%S} UTC", fill=(255, 255, 255), font=font)
    draw.text((6, 16), spec.name, fill=(220, 220, 220), font=font)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=QUALITY)
    return buf.getvalue()
