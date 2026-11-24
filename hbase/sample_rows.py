"""Put the Task 7.1 sample files into `media_catalog`: 11 photos, 1 video, 3 documents and 3 drawings.

The test table for the Task 12 design: real row keys and cells built from the committed samples in
`tests/fixtures/sources/`, before the catalogue load of Task 19 exists. Run in the client container with the
hbase profile up (the table is created if it is missing):

    python -m hbase.sample_rows

Photos read their time, position and device from EXIF. The project each photo is filed to is the expected
answer of `tests/fixtures/media/README.md`; the real rule is Task 19's. `meta:filing_rule` and `doc:doc_type`
hold the values Task 19 writes (contracts section 6, value sets). Videos, documents and drawings only have a
date, so their row key carries it at 00:00:00 (contracts section 8). Raw paths follow contracts section 5:
photos are in their day's SequenceFile (`seq_key` = original name); documents and videos carry
SAMPLE_INGESTED_AT as their ingest time, since nothing has been collected for these samples.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath

import piexif

from common import config, lake
from generators.media.exif import EXIF_TIME_FORMAT, from_dms
from hbase import catalogue
from tests.fixtures.make_sources import read_mtimes

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
SOURCES_DIR = FIXTURES_DIR / "sources"
SAMPLE_INGESTED_AT = datetime(2026, 11, 14, 12, 0, 0, tzinfo=timezone.utc)

# Expected filing of the sample photos (tests/fixtures/media/README.md); every other photo is UNASSIGNED.
FILED_TO = {
    "IMG_20260415_093000_00001.jpg": "FVE-2026-02",
    "IMG_20260520_101500_00001.jpg": "FVE-2026-02",
    "IMG_20190715_083000_00001.jpg": "FVE-2019-02",
    "IMG_20260708_073000_00001.jpg": "FVE-2026-02",
    "IMG_20260916_131500_00001.jpg": "FVE-2026-02",
}

# meta:filing_rule: the values of `media_files.filing_rule` (contracts section 6, Task 19).
RULE_GPS = "GPS"
RULE_NONE = "NONE"
RULE_FOLDER = "FOLDER"

# doc:doc_type by file stem: the values of `documents.doc_type` (contracts section 6, Task 19).
DOC_TYPES = {
    "contract": "CONTRACT",
    "building_permit": "PERMIT",
    "grid_connection": "GRID",
    "handover_protocol": "HANDOVER",
}
DRAWING_TYPE = "DRAWING"


def sample_rows(sources_dir: Path = SOURCES_DIR, fixtures_dir: Path = FIXTURES_DIR) -> dict[bytes, dict]:
    """Row key -> cells (as for `Table.put`) for every photo, video and project file in the samples."""
    dates = read_mtimes(fixtures_dir)
    rows: dict[bytes, dict] = {}
    for rel in sorted(dates):
        path = sources_dir / rel
        parts = PurePosixPath(rel).parts
        if parts[:2] == ("mailbox", "photos"):
            key, cells = _photo_row(path)
        elif parts[:2] == ("drive", "projects") and len(parts) == 5 and parts[3] == "videos":
            key, cells = _video_row(path, parts[2], dates[rel])
        elif parts[:2] == ("drive", "projects") and len(parts) == 4:
            key, cells = _document_row(path, parts[2], dates[rel])
        else:
            continue
        if key in rows:
            raise ValueError(f"two sample files give the row key {key.decode()}")
        rows[key] = cells
    return rows


def put_rows(conn, rows: dict[bytes, dict]) -> int:
    """Write the rows into `config.HBASE_TABLE` in one batch; return how many were written."""
    with conn.table(config.HBASE_TABLE).batch() as batch:
        for key, cells in rows.items():
            batch.put(key, cells)
    return len(rows)


def _photo_row(path: Path) -> tuple[bytes, dict]:
    data = path.read_bytes()
    ifds = piexif.load(data)
    taken_at = datetime.strptime(
        ifds["Exif"][piexif.ExifIFD.DateTimeOriginal].decode(), EXIF_TIME_FORMAT
    ).replace(tzinfo=timezone.utc)
    gps = ifds["GPS"]
    has_gps = piexif.GPSIFD.GPSLatitude in gps and piexif.GPSIFD.GPSLongitude in gps
    lat = lon = None
    if has_gps:
        lat = from_dms(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lon = from_dms(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
    project = FILED_TO.get(path.name, config.UNASSIGNED)
    rule = RULE_NONE if project == config.UNASSIGNED else RULE_GPS
    device = f"{ifds['0th'][piexif.ImageIFD.Make].decode()} {ifds['0th'][piexif.ImageIFD.Model].decode()}"
    file_id = _file_id(data)
    day = taken_at.date()
    families = {
        "meta": {
            "taken_at": taken_at,
            "lat": lat,
            "lon": lon,
            "size_bytes": len(data),
            "device": device,
            "original_name": path.name,
            "ext": path.suffix.lstrip(".").lower(),
            "filing_rule": rule,
        },
        "loc": {
            "raw_path": f"{config.LAKE_RAW}/photos/{day:%Y}/{day:%m}/{day:%Y-%m-%d}.seq",
            "seq_key": path.name,
        },
        "thumb": {"jpg": catalogue.thumbnail(data)},
    }
    return catalogue.row_key(project, "PHOTO", taken_at, file_id), catalogue.cells(families)


def _video_row(path: Path, project: str, business_date: date) -> tuple[bytes, dict]:
    data = path.read_bytes()
    ts = _key_time(business_date)
    families = {
        "meta": {
            "taken_at": ts,
            "size_bytes": len(data),
            "original_name": path.name,
            "ext": path.suffix.lstrip(".").lower(),
            "filing_rule": RULE_FOLDER,
        },
        "loc": {"raw_path": lake.raw_path("video", business_date, path.name, SAMPLE_INGESTED_AT, project)},
    }
    return catalogue.row_key(project, "VIDEO", ts, _file_id(data)), catalogue.cells(families)


def _document_row(path: Path, project: str, business_date: date) -> tuple[bytes, dict]:
    data = path.read_bytes()
    stem = path.stem
    is_drawing = path.suffix.lower() == ".dwg"
    version = None
    if is_drawing:
        doc_type, version = DRAWING_TYPE, stem.rpartition("_")[2]
    elif stem in DOC_TYPES:
        doc_type = DOC_TYPES[stem]
    else:
        raise ValueError(f"no doc_type for the sample file {path.name}")
    families = {
        "meta": {
            "size_bytes": len(data),
            "original_name": path.name,
            "ext": path.suffix.lstrip(".").lower(),
        },
        "loc": {"raw_path": lake.raw_path("docs", business_date, path.name, SAMPLE_INGESTED_AT, project)},
        "doc": {
            "doc_type": doc_type,
            "version": version,
            "is_final": (version == "final") if is_drawing else None,
            "title": stem.replace("_", " ").capitalize(),
            "file_date": business_date,
        },
    }
    kind = "DRAWING" if is_drawing else "DOC"
    ts = _key_time(business_date)
    return catalogue.row_key(project, kind, ts, _file_id(data)), catalogue.cells(families)


def _file_id(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[: catalogue.FILE_ID_LENGTH]


def _key_time(day: date) -> datetime:
    """00:00:00 of the date: the row-key time of a file that only has a date (contracts section 8)."""
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    rows = sample_rows()
    conn = catalogue.connect()
    try:
        catalogue.create_table(conn)
        written = put_rows(conn, rows)
    finally:
        conn.close()
    print(f"{config.HBASE_TABLE}: {written} sample rows written")


if __name__ == "__main__":
    main()
