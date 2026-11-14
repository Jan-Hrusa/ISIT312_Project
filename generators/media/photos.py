"""Site photos: which photos exist (plan), the planted problems, and the JPEG bytes (render).

Each signed project gets PHOTOS_PER_PROJECT photos over its whole construction period, taken on weekdays in
working hours within 90% of the site radius (so rounding never pushes a photo out of its site). For an ACTIVE
project only the part up to DATA_END exists. Then 10% of all photos lose their GPS (NO_GPS) and
WRONG_SITE_PER_SCALE x scale photos get a position at least WRONG_SITE_MIN_M from every project site.
"""

import io
import math
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from common import config
from common.projects import Project
from generators.media.util import distance_m, offset, workdays

PHOTOS_PER_PROJECT = (300, 400)  # over the full construction period
NO_GPS_SHARE = 0.10
WRONG_SITE_PER_SCALE = 5
WRONG_SITE_MIN_M = 10_000.0
SITE_SHARE = 0.9  # photos fall within this share of the radius
WORK_HOURS_UTC = (6, 16)  # first and last+1 hour (08:00-18:00 Czech summer time)
CZ_BOX = (48.6, 51.0, 12.1, 18.8)  # lat min, lat max, lon min, lon max: where wrong-site positions are drawn
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


def plan(projects: list[Project], rng, scale: int = 1, data_end: date = config.DATA_END) -> list[PhotoSpec]:
    """Every photo of every signed project, with the planted problems, sorted by name."""
    raw = []  # (taken_at, project_code, lat, lon, device)
    for p in projects:
        period = photo_period(p, data_end)
        if period is None:
            continue
        work = workdays(*period)
        if not work:
            continue
        full_days = (p.construction_end - p.construction_start).days + 1
        part_days = (period[1] - period[0]).days + 1
        count = round(rng.randint(*PHOTOS_PER_PROJECT) * part_days / full_days)
        for _ in range(count):
            day = rng.choice(work)
            second = rng.randrange(WORK_HOURS_UTC[0] * 3600, WORK_HOURS_UTC[1] * 3600)
            taken = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(seconds=second)
            bearing = rng.uniform(0, 2 * math.pi)
            dist = p.radius_m * SITE_SHARE * math.sqrt(rng.random())  # uniform over the disc
            lat, lon = offset(p.lat, p.lon, dist * math.cos(bearing), dist * math.sin(bearing))
            raw.append([taken, p.project_code, lat, lon, rng.choice(DEVICES), None])

    _plant(raw, projects, rng, scale)

    raw.sort(key=lambda r: (r[0], r[1]))
    per_day: dict[date, int] = {}
    specs = []
    for taken, code, lat, lon, device, planted in raw:
        n = per_day[taken.date()] = per_day.get(taken.date(), 0) + 1
        specs.append(PhotoSpec(photo_name(taken, n), taken, lat, lon, device, code, planted))
    return specs


def _plant(raw: list, projects: list[Project], rng, scale: int) -> None:
    """NO_GPS on NO_GPS_SHARE of the photos, WRONG_SITE on WRONG_SITE_PER_SCALE x scale others (in place)."""
    if not raw:
        return
    order = list(range(len(raw)))
    rng.shuffle(order)
    n_no_gps = round(len(raw) * NO_GPS_SHARE)
    n_wrong = min(WRONG_SITE_PER_SCALE * scale, len(raw) - n_no_gps)
    for i in order[:n_no_gps]:
        raw[i][2] = raw[i][3] = None
        raw[i][5] = "NO_GPS"
    for i in order[n_no_gps : n_no_gps + n_wrong]:
        raw[i][2], raw[i][3] = far_position(projects, rng)
        raw[i][5] = "WRONG_SITE"


def far_position(projects: list[Project], rng) -> tuple[float, float]:
    """A position in the Czech box at least WRONG_SITE_MIN_M from every project site."""
    lat_min, lat_max, lon_min, lon_max = CZ_BOX
    while True:
        lat, lon = round(rng.uniform(lat_min, lat_max), 6), round(rng.uniform(lon_min, lon_max), 6)
        if all(distance_m(lat, lon, p.lat, p.lon) >= WRONG_SITE_MIN_M for p in projects):
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
