"""The catalogue searches of hbase/search.py (Task 32.1), against a small HBase table made by each test."""

from __future__ import annotations

import socket
import uuid
from datetime import date, datetime, timezone

import pytest

from common import config
from hbase import catalogue, search
from hbase.sample_rows import sample_rows

PLANTED = "FVE-2022-08"  # the generator's wrong-version project (Task 7): final dated before v2


def _hbase_reachable() -> bool:
    try:
        with socket.create_connection((config.HBASE_HOST, config.HBASE_PORT), timeout=2):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _hbase_reachable(),
    reason=f"HBase Thrift {config.HBASE_HOST}:{config.HBASE_PORT} not reachable: start the stack with "
    "--profile hbase and run the tests in the client container",
)


def _drawing(project: str, version: str, day: date, file_id: str) -> tuple[bytes, dict[bytes, bytes]]:
    key = catalogue.row_key(project, "DRAWING", datetime.combine(day, datetime.min.time()), file_id)
    cells = catalogue.cells(
        {
            "meta": {"original_name": f"site_layout_{version}.dwg", "ext": "dwg", "filing_rule": "FOLDER"},
            "doc": {
                "doc_type": "DRAWING",
                "version": version,
                "is_final": version == search.FINAL,
                "title": f"Site layout {version}",
                "file_date": day,
            },
        }
    )
    return key, cells


@pytest.fixture
def catalogue_table(monkeypatch):
    """The Task 12 sample rows (FVE-2026-02: drawings v1 < v2 < final, 6 unassigned photos) plus the planted
    project's three drawings, in a table of its own that is dropped afterwards."""
    monkeypatch.setattr(config, "HBASE_TABLE", f"{config.HBASE_TABLE}_test_{uuid.uuid4().hex[:8]}")
    rows = sample_rows()
    for version, day, file_id in (
        ("v1", date(2022, 3, 1), "a000000000000001"),
        ("v2", date(2022, 5, 20), "a000000000000002"),
        ("final", date(2022, 4, 10), "a000000000000003"),
    ):
        key, cells = _drawing(PLANTED, version, day, file_id)
        rows[key] = cells
    conn = catalogue.connect()
    try:
        catalogue.create_table(conn)
        with conn.table(config.HBASE_TABLE).batch() as batch:
            for key, cells in rows.items():
                batch.put(key, cells)
        yield conn
    finally:
        if config.HBASE_TABLE.encode() in conn.tables():
            conn.delete_table(config.HBASE_TABLE, disable=True)
        conn.close()


def test_photos_range_inclusive(catalogue_table):
    # FVE-2026-02's filed sample photos: 15 Apr 09:30, 20 May 10:15, 8 Jul 07:30, 16 Sep 13:15 (UTC).
    names = [p["original_name"] for p in search.photos("FVE-2026-02", date(2026, 4, 15), date(2026, 7, 8))]
    assert names == [
        "IMG_20260415_093000_00001.jpg",
        "IMG_20260520_101500_00001.jpg",
        "IMG_20260708_073000_00001.jpg",
    ]  # both end days included, oldest first
    assert search.photos("FVE-2026-02", date(2026, 4, 16), date(2026, 7, 7))[0]["original_name"] == (
        "IMG_20260520_101500_00001.jpg"
    )
    assert search.photos("FVE-2026-02", date(2026, 7, 9), date(2026, 9, 15)) == []
    first = search.photos("FVE-2026-02", date(2026, 4, 15), date(2026, 4, 15))[0]
    assert first["taken_at"] == datetime(2026, 4, 15, 9, 30, tzinfo=timezone.utc)
    assert isinstance(first["lat"], float) and first["size_bytes"] > 0
    assert first["thumb"][:2] == b"\xff\xd8"  # the JPEG thumbnail comes with the photo


def test_latest_drawing_warning(catalogue_table):
    final, warning = search.latest_drawing(PLANTED)
    assert final["version"] == "final" and final["file_date"] == date(2022, 4, 10)
    assert warning == search.WARNING.format(version="v2")
    assert "v2 je novější než final" in warning

    final, warning = search.latest_drawing("FVE-2026-02")  # v1 < v2 < final: no warning
    assert (final["original_name"], warning) == ("site_layout_final.dwg", None)
    assert search.latest_drawing("FVE-2019-02") == (None, None)  # no drawings at all


def test_unassigned_prefix(catalogue_table):
    rows = search.unassigned()
    assert len(rows) == 6  # the 6 unassigned sample photos, nothing filed to a project
    assert {r["project_code"] for r in rows} == {config.UNASSIGNED}
    assert [r["key_time"] for r in rows] == sorted(
        (r["key_time"] for r in rows), reverse=True
    )  # newest first
    assert [r["original_name"] for r in search.unassigned("PHOTO", limit=2)] == [
        r["original_name"] for r in rows[:2]
    ]
    assert search.unassigned("VIDEO") == []
    assert all(r["thumb"] is None for r in rows)  # the list reads no thumbnails


@pytest.mark.integration
def test_q1_same_rows_in_both_stores():
    """After a full pipeline run: HBase and Hive return the same photos for E3's Q1 (default arguments)."""
    from benchmarks.e3 import run_e3

    conn = catalogue.connect()
    hive_conn, cursor = run_e3.hive_cursor()
    try:
        hbase_ids = run_e3.q1_hbase(conn, "FVE-2026-02", "2026-06")
        assert hbase_ids, "no photos of FVE-2026-02 in June 2026: run the pipeline on the main dataset first"
        assert hbase_ids == run_e3.q1_hive(cursor, "FVE-2026-02", "2026-06")
    finally:
        conn.close()
        hive_conn.close()
