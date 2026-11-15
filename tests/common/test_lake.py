"""Tests for common/lake.py: the raw path rule, the ingest log writer and the current file list."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from common import config, lake
from common.tables import read_table

INGESTED = datetime(2026, 11, 14, 9, 30, 0, tzinfo=timezone.utc)


def _row(original_path: str, raw_path: str, ingested_at: datetime, **changes) -> dict:
    row = {
        "run_id": ingested_at.strftime(lake.INGEST_TS_FORMAT),
        "source": "bank_gpc",
        "original_path": original_path,
        "raw_path": raw_path,
        "seq_key": None,
        "size_bytes": 130,
        "sha256": "a" * 64,
        "business_date": date(2026, 1, 2),
        "ingested_at": ingested_at,
    }
    row.update(changes)
    return row


def test_raw_path_rule(monkeypatch):
    monkeypatch.setattr(config, "LAKE_RAW", "/lake/raw")

    assert (
        lake.raw_path("bank_gpc", date(2026, 1, 2), "26001_2101234567_CZK.gpc", INGESTED)
        == "/lake/raw/bank_gpc/2026/01/26001_2101234567_CZK__20261114093000.gpc"
    )
    # Only the last extension is the extension; the month is zero-padded.
    assert (
        lake.raw_path("accounting", date(2025, 9, 29), "money_export_2025-W40.csv", INGESTED)
        == "/lake/raw/accounting/2025/09/money_export_2025-W40__20261114093000.csv"
    )
    assert (
        lake.raw_path("docs", date(2026, 1, 30), "contract.docx", INGESTED, project="FVE-2026-02")
        == "/lake/raw/docs/FVE-2026-02/2026/01/contract__20261114093000.docx"
    )
    assert (
        lake.raw_path("video", date(2026, 3, 9), "VID_20260309_00001.mp4", INGESTED, project="FVE-2026-02")
        == "/lake/raw/video/FVE-2026-02/2026/03/VID_20260309_00001__20261114093000.mp4"
    )

    with pytest.raises(ValueError, match="docs needs a project"):
        lake.raw_path("docs", date(2026, 1, 30), "contract.docx", INGESTED)
    with pytest.raises(ValueError, match="video needs a project"):
        lake.raw_path("video", date(2026, 3, 9), "VID_20260309_00001.mp4", INGESTED)
    with pytest.raises(ValueError, match="doesn't keep a project"):
        lake.raw_path("kpc", date(2026, 5, 19), "PO_2026-05-19_RB.kpc", INGESTED, project="FVE-2026-02")
    with pytest.raises(ValueError, match="SequenceFiles"):
        lake.raw_path("photos", date(2026, 5, 12), "IMG_20260512_101500_00042.jpg", INGESTED)
    with pytest.raises(ValueError, match="unknown source: nope"):
        lake.raw_path("nope", date(2026, 1, 2), "x.txt", INGESTED)


def test_raw_path_follows_the_dataset(monkeypatch):
    monkeypatch.setattr(config, "LAKE_RAW", "/bench/x10/lake/raw")
    assert lake.raw_path("kpc", date(2026, 5, 19), "PO_2026-05-19_RB.kpc", INGESTED).startswith(
        "/bench/x10/lake/raw/kpc/2026/05/"
    )


def test_append_ingest_log_appends_in_contract_order(clean_db):
    spark = clean_db
    first = _row("mailbox/bank/RB/26001_2101234567_CZK.gpc", "/lake/raw/bank_gpc/2026/01/a.gpc", INGESTED)
    second = _row(
        "mailbox/photos/IMG_20260512_101500_00042.jpg",
        "/lake/raw/photos/2026/05/2026-05-12.seq",
        INGESTED.replace(hour=10),
        source="photos",
        seq_key="IMG_20260512_101500_00042.jpg",
    )

    assert lake.append_ingest_log(spark, [first]) == 1
    assert lake.append_ingest_log(spark, [second]) == 1
    assert lake.append_ingest_log(spark, []) == 0

    rows = {r.source: r for r in read_table(spark, "ingest_log").collect()}
    assert set(rows) == {"bank_gpc", "photos"}
    gpc = rows["bank_gpc"]
    assert (gpc.run_id, gpc.original_path, gpc.raw_path) == (
        "20261114093000",
        "mailbox/bank/RB/26001_2101234567_CZK.gpc",
        "/lake/raw/bank_gpc/2026/01/a.gpc",
    )
    assert (gpc.seq_key, gpc.size_bytes, gpc.sha256) == (None, 130, "a" * 64)
    assert gpc.business_date == date(2026, 1, 2)
    assert gpc.ingested_at == datetime(2026, 11, 14, 9, 30, 0)
    assert rows["photos"].seq_key == "IMG_20260512_101500_00042.jpg"


def test_append_ingest_log_refuses_incomplete_rows(clean_db):
    row = _row("master/projects.csv", "/lake/raw/master/2026/10/projects.csv", INGESTED)
    del row["sha256"]
    with pytest.raises(ValueError, match="without sha256: 'master/projects.csv'"):
        lake.append_ingest_log(clean_db, [row])
    assert read_table(clean_db, "ingest_log").count() == 0


def test_current_raw_files_latest_version(clean_db):
    spark = clean_db
    later = INGESTED.replace(day=15)
    gpc = "mailbox/bank/RB/26001_2101234567_CZK.gpc"
    photo = "mailbox/photos/IMG_20260512_101500_00042.jpg"
    lake.append_ingest_log(
        spark,
        [
            _row(gpc, "/lake/raw/bank_gpc/2026/01/v1.gpc", INGESTED, sha256="1" * 64),
            _row(
                "mailbox/bank/RB/26002_2101234567_CZK.gpc", "/lake/raw/bank_gpc/2026/01/other.gpc", INGESTED
            ),
            _row(
                "drive/payments/PO_2026-05-19_RB.kpc", "/lake/raw/kpc/2026/05/po.kpc", INGESTED, source="kpc"
            ),
            _row(
                photo, "/lake/raw/photos/2026/05/2026-05-12.seq", INGESTED, source="photos", seq_key="IMG.jpg"
            ),
        ],
    )
    lake.append_ingest_log(
        spark,
        [
            _row(gpc, "/lake/raw/bank_gpc/2026/01/v2.gpc", later, sha256="2" * 64, size_bytes=260),
            _row(
                photo,
                "/lake/raw/photos/2026/05/2026-05-12__20261115093000.seq",
                later,
                source="photos",
                seq_key="IMG.jpg",
            ),
        ],
    )

    current = lake.current_raw_files(spark, "bank_gpc")
    assert tuple(current.columns) == lake.CURRENT_FILE_COLUMNS
    by_path = {r.original_path: r for r in current.collect()}
    assert set(by_path) == {gpc, "mailbox/bank/RB/26002_2101234567_CZK.gpc"}
    assert (by_path[gpc].raw_path, by_path[gpc].sha256, by_path[gpc].size_bytes) == (
        "/lake/raw/bank_gpc/2026/01/v2.gpc",
        "2" * 64,
        260,
    )
    assert by_path[gpc].seq_key is None
    assert by_path[gpc].business_date == date(2026, 1, 2)

    photos = lake.current_raw_files(spark, "photos").collect()
    assert [(r.seq_key, r.raw_path) for r in photos] == [
        ("IMG.jpg", "/lake/raw/photos/2026/05/2026-05-12__20261115093000.seq")
    ]
    assert lake.current_raw_files(spark, "isdoc").count() == 0
    with pytest.raises(ValueError, match="unknown source: nope"):
        lake.current_raw_files(spark, "nope")
