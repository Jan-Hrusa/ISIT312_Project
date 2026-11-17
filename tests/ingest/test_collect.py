"""Tests for the collection job (ingest/collect.py) on the fixture sources and a `file://` lake folder."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import ingest
from common import config, hdfs, lake
from common.tables import read_table
from ingest import collect as collect_module
from ingest.collect import collect
from tests.fixtures.make_sources import business_mtime, read_mtimes

RUN_1 = datetime(2026, 11, 14, 9, 30, 0, tzinfo=timezone.utc)
RUN_2 = RUN_1 + timedelta(days=1)


@pytest.fixture
def clock(monkeypatch):
    """Sets the run start of the next collect call (two real runs can fall into the same second)."""

    def set_now(moment: datetime) -> None:
        monkeypatch.setattr(collect_module, "_now", lambda: moment)

    set_now(RUN_1)
    return set_now


@pytest.fixture
def no_packer(monkeypatch):
    """The state before Task 18 is merged, whatever the checkout holds."""
    monkeypatch.setattr(collect_module, "_photo_packer", lambda: None)


def _files_per_source(root: Path) -> dict[str, list[str]]:
    return {
        source: sorted(p.relative_to(root).as_posix() for p in (root / spec.folder).glob(spec.pattern))
        for source, spec in config.RAW_SOURCES.items()
    }


def _write(path: Path, data: bytes, day: date) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.utime(path, (business_mtime(day), business_mtime(day)))
    return path


def _log(spark) -> list:
    return read_table(spark, "ingest_log").orderBy("ingested_at", "original_path").collect()


def test_ingest_log_row_per_file(clean_db, sources_tree, clock, no_packer):
    spark = clean_db
    expected = _files_per_source(sources_tree)
    dates = read_mtimes()

    stats = collect(spark, sources_tree)

    rows = _log(spark)
    logged = {(r.source, r.original_path) for r in rows}
    assert logged == {(s, f) for s, files in expected.items() if s != "photos" for f in files}
    assert len(rows) == len(logged)
    for source, files in expected.items():
        count = 0 if source == "photos" else len(files)
        assert (stats[source]["new"], stats[source]["skipped"]) == (count, 0), source
    for r in rows:
        local = sources_tree / r.original_path
        data = hdfs.read_bytes(spark, r.raw_path)
        assert data == local.read_bytes(), r.original_path
        assert r.sha256 == hashlib.sha256(data).hexdigest()
        assert r.size_bytes == len(data)
        assert r.business_date == dates[r.original_path]
        assert (r.run_id, r.seq_key) == ("20261114093000", None)
        assert r.ingested_at == RUN_1.replace(tzinfo=None)
        assert r.raw_path.startswith(f"{config.LAKE_RAW}/{r.source}/")
        assert r.raw_path.rsplit("/", 1)[1].startswith(f"{local.stem}__20261114093000")
    assert stats["master"]["bytes"] == sum((sources_tree / f).stat().st_size for f in expected["master"])


def test_second_run_collects_nothing(clean_db, sources_tree, clock, no_packer):
    spark = clean_db
    first = collect(spark, sources_tree)
    rows_before = read_table(spark, "ingest_log").count()

    clock(RUN_2)
    second = collect(spark, sources_tree)

    assert read_table(spark, "ingest_log").count() == rows_before
    for source in config.RAW_SOURCES:
        if source == "photos":
            continue
        assert second[source] == {"new": 0, "skipped": first[source]["new"], "bytes": 0}, source


def test_changed_file_gets_new_raw_name(clean_db, tmp_path, clock):
    spark = clean_db
    root = tmp_path / "sources"
    kpc = _write(root / "drive/payments/PO_2026-05-19_RB.kpc", b"first version", date(2026, 5, 19))
    collect(spark, root)

    _write(kpc, b"second version, corrected", date(2026, 5, 19))
    clock(RUN_2)
    stats = collect(spark, root)

    assert stats["kpc"] == {"new": 1, "skipped": 0, "bytes": 25}
    rows = _log(spark)
    assert [r.raw_path.rsplit("/", 1)[1] for r in rows] == [
        "PO_2026-05-19_RB__20261114093000.kpc",
        "PO_2026-05-19_RB__20261115093000.kpc",
    ]
    # Write-once: the first version is still there, unchanged.
    assert hdfs.read_bytes(spark, rows[0].raw_path) == b"first version"
    assert hdfs.read_bytes(spark, rows[1].raw_path) == b"second version, corrected"
    current = lake.current_raw_files(spark, "kpc").collect()
    assert [r.raw_path for r in current] == [rows[1].raw_path]


def test_existing_target_is_error(clean_db, tmp_path, clock):
    spark = clean_db
    root = tmp_path / "sources"
    local = _write(root / "drive/payments/PO_2026-05-19_RB.kpc", b"order", date(2026, 5, 19))
    target = lake.raw_path("kpc", date(2026, 5, 19), local.name, RUN_1)
    hdfs.mkdirs(spark, target.rsplit("/", 1)[0])
    Path(target.removeprefix("file://")).write_bytes(b"already there")

    with pytest.raises(FileExistsError, match="write-once"):
        collect(spark, root)

    assert hdfs.read_bytes(spark, target) == b"already there"
    assert read_table(spark, "ingest_log").count() == 0


def test_files_copied_before_a_failure_are_logged(clean_db, tmp_path, clock):
    spark = clean_db
    root = tmp_path / "sources"
    _write(root / "master/projects.csv", b"project_code\n", date(2026, 10, 31))
    blocked = _write(root / "drive/payments/PO_2026-05-19_RB.kpc", b"order", date(2026, 5, 19))
    target = lake.raw_path("kpc", date(2026, 5, 19), blocked.name, RUN_1)
    hdfs.mkdirs(spark, target.rsplit("/", 1)[0])
    Path(target.removeprefix("file://")).write_bytes(b"already there")

    with pytest.raises(FileExistsError):
        collect(spark, root)

    assert [r.original_path for r in _log(spark)] == ["master/projects.csv"]


def test_failure_among_parallel_copies_logs_every_copied_file(clean_db, tmp_path, clock):
    spark = clean_db
    root = tmp_path / "sources"
    for day in range(1, 29):
        _write(root / f"drive/payments/PO_2026-05-{day:02d}_RB.kpc", b"order %d" % day, date(2026, 5, day))
    blocked = lake.raw_path("kpc", date(2026, 5, 14), "PO_2026-05-14_RB.kpc", RUN_1)
    hdfs.mkdirs(spark, blocked.rsplit("/", 1)[0])
    Path(blocked.removeprefix("file://")).write_bytes(b"already there")

    with pytest.raises(FileExistsError):
        collect(spark, root)

    in_raw = {entry.rsplit("/", 1)[1] for entry in hdfs.ls(spark, blocked.rsplit("/", 1)[0])}
    in_raw = {name for name in in_raw if name.endswith(".kpc")}
    assert {r.raw_path.rsplit("/", 1)[1] for r in _log(spark)} == in_raw - {blocked.rsplit("/", 1)[1]}

    # The next run (a second later, so new raw names) collects what is still missing, the blocked file too.
    clock(RUN_2)
    stats = collect(spark, root)
    assert stats["kpc"]["new"] + stats["kpc"]["skipped"] == 28
    assert lake.current_raw_files(spark, "kpc").count() == 28


def test_business_month_from_mtime(clean_db, tmp_path, clock):
    spark = clean_db
    root = tmp_path / "sources"
    # The names say nothing about the date (or something else): only the mtime counts.
    _write(root / "mailbox/bank/RB/26001_2101234567_CZK.gpc", b"074", date(2024, 2, 29))
    _write(root / "drive/accounting/money_export_2026-W20.csv", b"doc_ref\n", date(2025, 12, 31))

    collect(spark, root)

    rows = {r.source: r for r in _log(spark)}
    assert rows["bank_gpc"].raw_path == (
        f"{config.LAKE_RAW}/bank_gpc/2024/02/26001_2101234567_CZK__20261114093000.gpc"
    )
    assert rows["bank_gpc"].business_date == date(2024, 2, 29)
    assert rows["accounting"].raw_path == (
        f"{config.LAKE_RAW}/accounting/2025/12/money_export_2026-W20__20261114093000.csv"
    )
    assert rows["accounting"].business_date == date(2025, 12, 31)


def test_identical_bytes_different_paths_all_collected(clean_db, tmp_path, clock):
    spark = clean_db
    root = tmp_path / "sources"
    header = b"doc_ref;supplier_ico;vs\n"
    _write(root / "drive/accounting/money_export_2026-W01.csv", header, date(2025, 12, 29))
    _write(root / "drive/accounting/money_export_2026-W02.csv", header, date(2026, 1, 5))
    _write(root / "mailbox/bank/RB/26001_2101234567_CZK.txt", b"", date(2026, 1, 2))
    _write(root / "mailbox/bank/RB/26002_2101234567_CZK.txt", b"", date(2026, 1, 5))

    stats = collect(spark, root)

    assert stats["accounting"]["new"] == 2
    assert stats["bank_txt"]["new"] == 2
    rows = _log(spark)
    assert len(rows) == 4
    assert len({r.raw_path for r in rows}) == 4
    assert len({r.sha256 for r in rows}) == 2

    clock(RUN_2)
    again = collect(spark, root)
    assert (again["accounting"]["skipped"], again["bank_txt"]["skipped"]) == (2, 2)
    assert len(_log(spark)) == 4


def test_docs_and_videos_keep_their_project(clean_db, sources_tree, clock, no_packer):
    spark = clean_db
    collect(spark, sources_tree, sources=["docs", "video"])

    rows = _log(spark)
    assert {r.source for r in rows} == {"docs", "video"}
    docs = [r for r in rows if r.source == "docs"]
    videos = [r for r in rows if r.source == "video"]
    assert docs and videos
    assert all(r.raw_path.startswith(f"{config.LAKE_RAW}/docs/FVE-2026-02/") for r in docs)
    assert all(r.raw_path.startswith(f"{config.LAKE_RAW}/video/FVE-2026-02/") for r in videos)
    # A video is not also a document: `docs` are the files directly in the project folder.
    assert not any(r.original_path.endswith(".mp4") for r in docs)
    assert all("/videos/" in r.original_path for r in videos)


def test_folder_that_is_not_a_project_is_an_error(clean_db, tmp_path, clock):
    root = tmp_path / "sources"
    _write(root / "drive/projects/old stuff/contract.docx", b"docx", date(2026, 1, 30))

    with pytest.raises(ValueError, match="'old stuff' is not a project code"):
        collect(clean_db, root)
    assert read_table(clean_db, "ingest_log").count() == 0


def test_photos_skipped_until_packer_is_merged(clean_db, sources_tree, clock, no_packer, capsys):
    spark = clean_db
    stats = collect(spark, sources_tree, sources=["photos", "kpc"])

    out = capsys.readouterr().out.splitlines()
    assert "photos: SKIPPED (packer not merged)" in out
    assert any(line.startswith("kpc: 1 new, 0 skipped, ") and line.endswith(" MB") for line in out)
    assert stats["photos"] == {"new": 0, "skipped": 0, "bytes": 0}
    assert {r.source for r in _log(spark)} == {"kpc"}
    assert not hdfs.exists(spark, f"{config.LAKE_RAW}/photos")


def test_photos_go_to_the_packer_once(clean_db, sources_tree, clock, monkeypatch):
    spark = clean_db
    photos = _files_per_source(sources_tree)["photos"]
    dates = read_mtimes()
    calls = []

    def pack(spark_arg, files, run_id, ingested_at):
        calls.append((files, run_id, ingested_at))
        return [
            {
                "run_id": run_id,
                "source": "photos",
                "original_path": f["original_path"],
                "raw_path": f"{config.LAKE_RAW}/photos/{f['business_date']:%Y/%m/%Y-%m-%d}.seq",
                "seq_key": Path(f["local_path"]).name,
                "size_bytes": f["size_bytes"],
                "sha256": f["sha256"],
                "business_date": f["business_date"],
                "ingested_at": ingested_at,
            }
            for f in files
        ]

    monkeypatch.setattr(collect_module, "_photo_packer", lambda: pack)

    stats = collect(spark, sources_tree, sources=["photos"])

    assert len(calls) == 1
    files, run_id, ingested_at = calls[0]
    assert (run_id, ingested_at) == ("20261114093000", RUN_1)
    assert [f["original_path"] for f in files] == photos
    for f in files:
        local = sources_tree / f["original_path"]
        assert set(f) == {"local_path", "original_path", "business_date", "sha256", "size_bytes"}
        assert Path(f["local_path"]) == local
        assert f["business_date"] == dates[f["original_path"]]
        assert f["sha256"] == hashlib.sha256(local.read_bytes()).hexdigest()
        assert f["size_bytes"] == local.stat().st_size
    assert stats["photos"]["new"] == len(photos)
    assert stats["photos"]["bytes"] == sum(f["size_bytes"] for f in files)
    rows = _log(spark)
    assert [r.original_path for r in rows] == photos
    assert all(r.seq_key == r.original_path.rsplit("/", 1)[1] for r in rows)

    # The packer's rows are in the log, so a second run hands it nothing.
    clock(RUN_2)
    again = collect(spark, sources_tree, sources=["photos"])
    assert len(calls) == 1
    assert again["photos"] == {"new": 0, "skipped": len(photos), "bytes": 0}
    assert lake.current_raw_files(spark, "photos").count() == len(photos)


def test_dry_run_copies_and_logs_nothing(clean_db, sources_tree, clock, no_packer):
    spark = clean_db
    expected = _files_per_source(sources_tree)

    stats = collect(spark, sources_tree, dry_run=True)

    assert stats["isdoc"]["new"] == len(expected["isdoc"])
    assert read_table(spark, "ingest_log").count() == 0
    assert not hdfs.exists(spark, config.LAKE_RAW)


def test_sources_filter(clean_db, sources_tree, clock):
    spark = clean_db
    stats = collect(spark, sources_tree, sources=["master"])

    assert list(stats) == ["master"]
    assert {r.source for r in _log(spark)} == {"master"}
    with pytest.raises(ValueError, match="unknown source: nope"):
        collect(spark, sources_tree, sources=["master", "nope"])


def test_run_returns_the_totals(clean_db, sources_tree, clock, no_packer, monkeypatch):
    spark = clean_db
    monkeypatch.setattr(config, "SOURCES_DIR", sources_tree)

    # Mock HDFS snapshot operations because this test uses a local filesystem.
    monkeypatch.setattr("ingest.snapshot.config.DATASET", "main")
    monkeypatch.setattr("ingest.snapshot.ensure_snapshottable", lambda spark: None)
    monkeypatch.setattr("ingest.snapshot.take", lambda spark, run_id: "/fake/snapshot")
    monkeypatch.setattr("ingest.snapshot.prune", lambda spark: None)

    collected = sum(len(f) for s, f in _files_per_source(sources_tree).items() if s != "photos")

    assert ingest.run(spark) == {
        "files_new": collected,
        "files_skipped": 0,
        "snapshot": 1,
    }

    clock(RUN_2)

    assert ingest.run(spark) == {
        "files_new": 0,
        "files_skipped": collected,
        "snapshot": 1,
    }
