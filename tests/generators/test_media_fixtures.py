"""The Task 7.1 media fixtures match tests/fixtures/media/README.md."""

import hashlib
import math
import re
import struct
from datetime import date, datetime, timezone
from pathlib import Path

import piexif

from common.projects import load_projects
from tests.fixtures.make_sources import make_sources, read_mtimes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SOURCES = FIXTURES / "sources"
README = FIXTURES / "media" / "README.md"
PROJECT_DIR = SOURCES / "drive" / "projects" / "FVE-2026-02"


def _table_rows(prefix: str) -> list[list[str]]:
    """Cells of the README table rows whose first cell starts with prefix."""
    rows = []
    for line in README.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0].startswith(prefix):
            rows.append(cells)
    return rows


def _dms(value) -> float:
    (dn, dd), (mn, md), (sn, sd) = value
    return dn / dd + mn / md / 60 + sn / sd / 3600


def _distance_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _expected_filing(lat, lon, day, projects) -> str:
    for p in projects:
        if not p.is_signed or p.construction_start is None:
            continue
        inside = _distance_m(lat, lon, p.lat, p.lon) <= p.radius_m
        if inside and p.construction_start <= day <= p.construction_end:
            return p.project_code
    return "UNASSIGNED"


def test_media_fixtures_match_readme():
    photos = _table_rows("IMG_")
    described = [r for r in photos if len(r) == 8]
    assert len(described) == 11
    projects = load_projects(SOURCES / "master" / "projects.csv")
    on_disk = sorted(p.name for p in (SOURCES / "mailbox" / "photos").glob("*.jpg"))
    assert on_disk == sorted(r[0] for r in described)

    for name, taken_at, lat, lon, device, _distance, filed_to, issue in described:
        ifds = piexif.load(str(SOURCES / "mailbox" / "photos" / name))
        taken = datetime.strptime(taken_at, "%Y-%m-%d %H:%M:%S")
        assert ifds["Exif"][piexif.ExifIFD.DateTimeOriginal] == taken.strftime("%Y:%m:%d %H:%M:%S").encode()
        make = ifds["0th"][piexif.ImageIFD.Make].decode()
        model = ifds["0th"][piexif.ImageIFD.Model].decode()
        assert f"{make} {model}" == device
        gps = ifds["GPS"]
        if lat == "none":
            assert piexif.GPSIFD.GPSLatitude not in gps and piexif.GPSIFD.GPSLongitude not in gps
            assert (filed_to, issue) == ("UNASSIGNED", "NO_GPS")
            continue
        assert gps[piexif.GPSIFD.GPSLatitudeRef] == b"N" and gps[piexif.GPSIFD.GPSLongitudeRef] == b"E"
        got_lat, got_lon = _dms(gps[piexif.GPSIFD.GPSLatitude]), _dms(gps[piexif.GPSIFD.GPSLongitude])
        assert abs(got_lat - float(lat)) < 1e-6 and abs(got_lon - float(lon)) < 1e-6
        assert gps[piexif.GPSIFD.GPSDateStamp] == taken.strftime("%Y:%m:%d").encode()
        assert _expected_filing(got_lat, got_lon, taken.date(), projects) == filed_to
        assert (issue == "–") == (filed_to != "UNASSIGNED")

    for name, file_id, size in (r for r in photos if len(r) == 3):
        data = (SOURCES / "mailbox" / "photos" / name).read_bytes()
        assert (hashlib.sha256(data).hexdigest()[:16], len(data)) == (file_id, int(size))


def test_media_fixture_documents_and_video():
    rows = {r[0]: r for r in _table_rows("") if len(r) == 5 and re.match(r"^[\w/]+\.\w+$", r[0])}
    files = sorted(p.relative_to(PROJECT_DIR).as_posix() for p in PROJECT_DIR.rglob("*") if p.is_file())
    assert files == sorted(rows)
    dates = read_mtimes(FIXTURES)
    for rel, (_, business, _kind, file_id, size) in rows.items():
        data = (PROJECT_DIR / rel).read_bytes()
        assert (hashlib.sha256(data).hexdigest()[:16], len(data)) == (file_id, int(size))
        assert dates[f"drive/projects/FVE-2026-02/{rel}"] == date.fromisoformat(business[:10])

    drawing_dates = [dates[f"drive/projects/FVE-2026-02/site_layout_{v}.dwg"] for v in ("v1", "v2", "final")]
    assert drawing_dates == sorted(drawing_dates) and len(set(drawing_dates)) == 3
    for v in ("v1", "v2", "final"):
        assert (
            (PROJECT_DIR / f"site_layout_{v}.dwg")
            .read_bytes()
            .startswith(b"AC1032\x00SYNTHETIC SITE LAYOUT FVE-2026-02 " + v.encode())
        )
    assert (PROJECT_DIR / "contract.docx").read_bytes()[:2] == b"PK"
    assert (PROJECT_DIR / "building_permit.pdf").read_bytes()[:5] == b"%PDF-"

    sample = (FIXTURES / "media" / "sample.mp4").read_bytes()
    assert sample[4:8] == b"ftyp"
    video = (PROJECT_DIR / "videos" / "VID_20260520_00001.mp4").read_bytes()
    name = b"VID_20260520_00001.mp4"
    assert video == sample + struct.pack(">I", 8 + len(name)) + b"free" + name


def test_media_fixture_mtimes(tmp_path):
    tree = make_sources(tmp_path / "sources")
    for rel, day in read_mtimes(FIXTURES).items():
        if rel.startswith(("mailbox/photos/", "drive/projects/")):
            mtime = datetime.fromtimestamp((tree / rel).stat().st_mtime, timezone.utc)
            assert mtime == datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
