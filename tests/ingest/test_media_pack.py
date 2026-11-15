"""Tests for photo packing (ingest/media_pack.py, ingest/seqfile.py) on the fixture photos and a `file://`
lake folder: SequenceFiles work on the local file system too."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from common import config, lake
from common.schemas import CLEAN_TABLES
from common.tables import read_table
from ingest import collect as collect_module
from ingest import media_pack
from ingest.collect import collect
from ingest.media_pack import pack
from ingest.seqfile import read_seq, write_seq
from tests.fixtures.make_sources import business_mtime, read_mtimes

RUN_1 = datetime(2026, 11, 14, 9, 30, 0, tzinfo=timezone.utc)
RUN_2 = RUN_1 + timedelta(days=1)


@pytest.fixture
def lake_raw(tmp_path, monkeypatch) -> Path:
    """A `file://` raw zone in a temporary folder (common.config redirected for the test)."""
    root = tmp_path / "lake"
    monkeypatch.setattr(config, "LAKE_ROOT", root.as_uri())
    monkeypatch.setattr(config, "LAKE_RAW", f"{root.as_uri()}/raw")
    return root / "raw"


def _photo(path: Path, root: Path, day: date | None = None) -> dict:
    """The dict collect hands the packer for one photo (business date = mtime date unless `day` is given)."""
    data = path.read_bytes()
    mtime_day = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date()
    return {
        "local_path": str(path),
        "original_path": path.relative_to(root).as_posix(),
        "business_date": day or mtime_day,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _fixture_photos(sources_tree: Path) -> list[dict]:
    return [_photo(p, sources_tree) for p in sorted((sources_tree / "mailbox" / "photos").glob("*.jpg"))]


def _seq_files(lake_raw: Path) -> list[str]:
    """The .seq files under the raw photos folder, relative to it (Hadoop's .crc side files left out)."""
    root = lake_raw / "photos"
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.seq"))


def _write_photo(path: Path, data: bytes, day: date) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (business_mtime(day), business_mtime(day)))
    return path


def test_one_seq_per_day(spark, sources_tree, lake_raw):
    photos = _fixture_photos(sources_tree)
    days = sorted({p["business_date"] for p in photos})
    assert len(days) < len(photos)  # the fixture has days with several photos

    pack(spark, photos, "20261114093000", RUN_1)

    assert _seq_files(lake_raw) == [f"{d:%Y}/{d:%m}/{d:%Y-%m-%d}.seq" for d in days]
    for day in days:
        expected = sorted(Path(p["original_path"]).name for p in photos if p["business_date"] == day)
        keys = [key for key, _ in read_seq(spark, media_pack.day_path(day)).collect()]
        assert keys == expected


def test_roundtrip_bytes_identical(spark, sources_tree, lake_raw):
    photos = _fixture_photos(sources_tree)
    rows = pack(spark, photos, "20261114093000", RUN_1)

    read_back = {}
    for raw_path in sorted({r["raw_path"] for r in rows}):
        for key, data in read_seq(spark, raw_path).collect():
            read_back[(raw_path, key)] = data
    assert len(read_back) == len(photos)
    for row in rows:
        data = read_back[(row["raw_path"], row["seq_key"])]
        assert isinstance(data, bytes) and len(data) == row["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        assert data == (sources_tree / row["original_path"]).read_bytes()


def test_existing_day_gets_new_file(spark, sources_tree, lake_raw, tmp_path):
    photos = _fixture_photos(sources_tree)
    pack(spark, photos, "20261114093000", RUN_1)
    first = lake_raw / "photos" / "2026" / "05" / "2026-05-20.seq"
    before = first.read_bytes()

    # A later run brings a new photo of a day that is already packed.
    later = tmp_path / "later"
    data = (sources_tree / "mailbox/photos/IMG_20260520_101500_00001.jpg").read_bytes() + b"\x00"
    new = _photo(
        _write_photo(later / "mailbox/photos/IMG_20260520_170000_00009.jpg", data, date(2026, 5, 20)), later
    )
    rows = pack(spark, [new], "20261115093000", RUN_2)

    expected = media_pack.day_path(date(2026, 5, 20)).replace(".seq", "__20261115093000.seq")
    assert [r["raw_path"] for r in rows] == [expected]
    assert first.read_bytes() == before
    assert "2026/05/2026-05-20__20261115093000.seq" in _seq_files(lake_raw)
    assert read_seq(spark, expected).collect() == [("IMG_20260520_170000_00009.jpg", data)]


def test_returns_row_per_photo(spark, sources_tree, lake_raw):
    photos = _fixture_photos(sources_tree)
    rows = pack(spark, photos, "20261114093000", RUN_1)

    columns = [name for name, _ in CLEAN_TABLES["ingest_log"]]
    assert len(rows) == len(photos)
    assert sorted(r["original_path"] for r in rows) == sorted(p["original_path"] for p in photos)
    by_path = {p["original_path"]: p for p in photos}
    for row in rows:
        photo = by_path[row["original_path"]]
        assert list(row) == columns
        assert all(row[c] is not None for c in columns)
        assert row["run_id"] == "20261114093000" and row["ingested_at"] == RUN_1
        assert row["source"] == "photos"
        assert row["seq_key"] == Path(photo["original_path"]).name
        assert row["raw_path"] == media_pack.day_path(photo["business_date"])
        assert (row["size_bytes"], row["sha256"]) == (photo["size_bytes"], photo["sha256"])
        assert row["business_date"] == photo["business_date"]


def test_day_from_business_date(spark, sources_tree, lake_raw):
    # The day is the business date collect passes in (the mtime), never the name or EXIF.
    path = sources_tree / "mailbox/photos/IMG_20260415_093000_00001.jpg"
    photo = _photo(path, sources_tree, day=date(2026, 6, 1))
    dates = read_mtimes()
    assert dates[photo["original_path"]] == date(2026, 4, 15)

    rows = pack(spark, [photo], "20261114093000", RUN_1)

    assert _seq_files(lake_raw) == ["2026/06/2026-06-01.seq"]
    assert rows[0]["business_date"] == date(2026, 6, 1)
    assert rows[0]["raw_path"] == media_pack.day_path(date(2026, 6, 1))
    assert media_pack.day_path(date(2026, 6, 1)) == f"{config.LAKE_RAW}/photos/2026/06/2026-06-01.seq"


def test_rows_have_original_path(clean_db, sources_tree, monkeypatch):
    # Through the real collection job: the packer's rows land in ingest_log, so a second collect
    # packs nothing.
    spark = clean_db
    monkeypatch.setattr(collect_module, "_now", lambda: RUN_1)
    photos = sorted(
        p.relative_to(sources_tree).as_posix() for p in (sources_tree / "mailbox/photos").glob("*.jpg")
    )

    stats = collect(spark, sources_tree, sources=["photos"])

    assert stats["photos"]["new"] == len(photos)
    rows = read_table(spark, "ingest_log").orderBy("original_path").collect()
    assert [r.original_path for r in rows] == photos
    assert all(r.source == "photos" and r.raw_path.endswith(".seq") for r in rows)
    current = lake.current_raw_files(spark, "photos").collect()
    assert len(current) == len(photos)
    seq_files = {r.raw_path for r in rows}
    assert len(seq_files) == len({r.business_date for r in rows})

    monkeypatch.setattr(collect_module, "_now", lambda: RUN_2)
    again = collect(spark, sources_tree, sources=["photos"])

    assert again["photos"] == {"new": 0, "skipped": len(photos), "bytes": 0}
    assert read_table(spark, "ingest_log").count() == len(photos)
    assert not list((Path(config.LAKE_RAW.removeprefix("file://")) / "photos").rglob("*__*.seq"))


def test_changed_photo_is_an_error(spark, sources_tree, lake_raw):
    photo = _fixture_photos(sources_tree)[0]
    photo["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="changed since it was hashed"):
        pack(spark, [photo], "20261114093000", RUN_1)
    assert not (lake_raw / "photos").exists() or _seq_files(lake_raw) == []


def test_write_seq_refuses_existing_file(spark, lake_raw):
    path = f"{config.LAKE_RAW}/photos/2026/05/2026-05-20.seq"
    assert write_seq(spark, path, [("a.jpg", b"\xff\xd8a"), ("b.jpg", b"")]) == 2
    with pytest.raises(FileExistsError, match="write-once"):
        write_seq(spark, path, [("c.jpg", b"c")])
    assert read_seq(spark, path).collect() == [("a.jpg", b"\xff\xd8a"), ("b.jpg", b"")]


def test_empty_batch_writes_nothing(spark, lake_raw):
    assert pack(spark, [], "20261114093000", RUN_1) == []
    assert not (lake_raw / "photos").exists()
