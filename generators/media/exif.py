"""EXIF for the synthetic site photos (piexif): capture time, camera and GPS position.

DateTimeOriginal holds the UTC time (EXIF has no time zone; the contract keeps every timestamp in UTC), and
GPSDateStamp / GPSTimeStamp repeat it, as GPS time is UTC by definition. A photo without a position simply has
no GPS IFD (the NO_GPS case).
"""

import io
from datetime import datetime, timezone

import piexif

EXIF_TIME_FORMAT = "%Y:%m:%d %H:%M:%S"
SECONDS_DENOMINATOR = (
    10_000  # 1/10000 of an arc second: about 3 mm, so 6 decimal places survive the round trip
)


def to_dms(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    """Decimal degrees (sign ignored) -> EXIF degrees, minutes, seconds as rationals."""
    value = abs(value)
    degrees = int(value)
    minutes_full = (value - degrees) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60 * SECONDS_DENOMINATOR)
    if seconds >= 60 * SECONDS_DENOMINATOR:  # rounding up to a full minute
        seconds -= 60 * SECONDS_DENOMINATOR
        minutes += 1
    if minutes == 60:
        minutes = 0
        degrees += 1
    return (degrees, 1), (minutes, 1), (seconds, SECONDS_DENOMINATOR)


def from_dms(dms, ref: bytes | str) -> float:
    """EXIF degrees, minutes, seconds rationals and a reference (N/S/E/W) -> signed decimal degrees."""
    (dn, dd), (mn, md), (sn, sd) = dms
    value = dn / dd + mn / md / 60 + sn / sd / 3600
    ref = ref.decode() if isinstance(ref, bytes) else ref
    return -value if ref in ("S", "W") else value


def add(
    jpeg: bytes, taken_at: datetime, lat: float | None, lon: float | None, device: tuple[str, str]
) -> bytes:
    """The JPEG with DateTimeOriginal, Make/Model and (when lat/lon are given) a GPS IFD."""
    utc = taken_at.astimezone(timezone.utc)
    make, model = device
    ifds = {
        "0th": {piexif.ImageIFD.Make: make.encode(), piexif.ImageIFD.Model: model.encode()},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: utc.strftime(EXIF_TIME_FORMAT).encode()},
        "GPS": {},
    }
    if lat is not None and lon is not None:
        ifds["GPS"] = {
            piexif.GPSIFD.GPSVersionID: (2, 2, 0, 0),
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
            piexif.GPSIFD.GPSLatitude: to_dms(lat),
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
            piexif.GPSIFD.GPSLongitude: to_dms(lon),
            piexif.GPSIFD.GPSTimeStamp: ((utc.hour, 1), (utc.minute, 1), (utc.second, 1)),
            piexif.GPSIFD.GPSDateStamp: utc.strftime("%Y:%m:%d").encode(),
        }
    out = io.BytesIO()
    piexif.insert(piexif.dump(ifds), jpeg, out)
    return out.getvalue()


def read(jpeg: bytes) -> dict:
    """taken_at (UTC datetime), lat, lon (None without GPS) and device (make, model) from a photo's EXIF."""
    ifds = piexif.load(jpeg)
    taken = ifds["Exif"].get(piexif.ExifIFD.DateTimeOriginal)
    gps = ifds.get("GPS") or {}
    lat = lon = None
    if piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps:
        lat = from_dms(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = from_dms(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
    return {
        "taken_at": (
            datetime.strptime(taken.decode(), EXIF_TIME_FORMAT).replace(tzinfo=timezone.utc)
            if taken
            else None
        ),
        "lat": lat,
        "lon": lon,
        "device": (
            ifds["0th"].get(piexif.ImageIFD.Make, b"").decode(),
            ifds["0th"].get(piexif.ImageIFD.Model, b"").decode(),
        ),
    }
