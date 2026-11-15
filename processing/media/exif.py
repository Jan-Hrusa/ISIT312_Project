"""Capture time, position and camera of a photo from its EXIF (written by generators/media/exif.py, Task 7).

DateTimeOriginal holds the UTC time (the contract keeps every timestamp in UTC); a photo without a position
has no GPS IFD at all. Anything unreadable comes back as None, so one damaged photo never stops the job: it is
filed as having no time or position.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

import piexif

from generators.media.exif import EXIF_TIME_FORMAT, from_dms


class PhotoExif(NamedTuple):
    taken_at: datetime | None  # UTC, timezone-aware
    lat: float | None
    lon: float | None
    device: str | None  # "<Make> <Model>"


def read(data: bytes) -> PhotoExif:
    """The EXIF fields of one JPEG's bytes; None for each field that is missing or unreadable."""
    try:
        ifds = piexif.load(bytes(data))
    except Exception:  # piexif raises several types for damaged or non-JPEG bytes
        return PhotoExif(None, None, None, None)
    return PhotoExif(_taken_at(ifds), *_position(ifds), _device(ifds))


def _taken_at(ifds: dict) -> datetime | None:
    raw = ifds.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
    if not raw:
        return None
    try:
        return datetime.strptime(raw.decode("ascii"), EXIF_TIME_FORMAT).replace(tzinfo=timezone.utc)
    except (UnicodeDecodeError, ValueError):
        return None


def _position(ifds: dict) -> tuple[float | None, float | None]:
    gps = ifds.get("GPS", {})
    try:
        lat = from_dms(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = from_dms(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None, None
    return lat, lon


def _device(ifds: dict) -> str | None:
    zeroth = ifds.get("0th", {})
    parts = [zeroth.get(tag) for tag in (piexif.ImageIFD.Make, piexif.ImageIFD.Model)]
    text = " ".join(p.decode("utf-8", "replace").strip("\x00 ") for p in parts if p)
    return text or None
