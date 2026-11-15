"""Row keys and scans of the HBase catalogue (Task 12)."""

import io
import socket
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from PIL import Image

from common import config
from hbase import catalogue
from hbase.sample_rows import FILED_TO, put_rows, sample_rows

FILE_ID = "00c7ce529644981b"


def _hbase_reachable() -> bool:
    try:
        with socket.create_connection((config.HBASE_HOST, config.HBASE_PORT), timeout=2):
            return True
    except OSError:
        return False


def test_row_key_format():
    ts = datetime(2026, 4, 15, 9, 30, 0)
    assert catalogue.row_key("FVE-2026-02", "PHOTO", ts, FILE_ID) == b"FVE-2026-02#PHOTO#20260415093000#" + (
        FILE_ID.encode()
    )
    # An aware time is stored in UTC: 11:30 in Prague (CEST, UTC+2) is 09:30 UTC.
    prague = datetime(2026, 4, 15, 11, 30, 0, tzinfo=timezone(timedelta(hours=2)))
    assert catalogue.row_key("FVE-2026-02", "PHOTO", prague, FILE_ID) == catalogue.row_key(
        "FVE-2026-02", "PHOTO", ts, FILE_ID
    )
    assert catalogue.row_key(config.UNASSIGNED, "PHOTO", ts, FILE_ID).startswith(b"UNASSIGNED#PHOTO#")
    for bad in (
        ("FVE-26-02", "PHOTO", FILE_ID),
        ("FVE-2026-02", "IMAGE", FILE_ID),
        ("FVE-2026-02", "PHOTO", "00C7CE529644981B"),
        ("FVE-2026-02", "PHOTO", FILE_ID[:-1]),
    ):
        project, kind, file_id = bad
        with pytest.raises(ValueError):
            catalogue.row_key(project, kind, ts, file_id)


def test_byte_order_equals_time_order():
    times = [
        datetime(2026, 1, 1, 0, 0, 0),
        datetime(2026, 1, 1, 0, 0, 9),
        datetime(2026, 1, 1, 0, 0, 10),
        datetime(2026, 1, 1, 9, 59, 59),
        datetime(2026, 1, 1, 10, 0, 0),
        datetime(2026, 9, 30, 23, 59, 59),
        datetime(2026, 10, 1, 0, 0, 0),
        datetime(2027, 1, 1, 0, 0, 0),
    ]
    keys = [catalogue.row_key("FVE-2026-02", "PHOTO", t, FILE_ID) for t in reversed(times)]
    assert sorted(keys) == [catalogue.row_key("FVE-2026-02", "PHOTO", t, FILE_ID) for t in times]


def test_scan_bounds_include_end_day():
    start, stop = catalogue.scan_bounds("FVE-2026-02", "PHOTO", date(2026, 6, 1), date(2026, 9, 1))
    assert start == b"FVE-2026-02#PHOTO#20260601000000"
    assert stop == b"FVE-2026-02#PHOTO#20260902000000"

    def key(t):
        return catalogue.row_key("FVE-2026-02", "PHOTO", t, FILE_ID)

    assert start <= key(datetime(2026, 6, 1, 0, 0, 0)) < stop
    assert start <= key(datetime(2026, 9, 1, 23, 59, 59)) < stop
    assert not key(datetime(2026, 5, 31, 23, 59, 59)) >= start
    assert not key(datetime(2026, 9, 2, 0, 0, 0)) < stop
    # One day: the start and the end are the same date.
    one = catalogue.scan_bounds("FVE-2026-02", "PHOTO", date(2026, 5, 20), date(2026, 5, 20))
    assert one == (b"FVE-2026-02#PHOTO#20260520000000", b"FVE-2026-02#PHOTO#20260521000000")
    with pytest.raises(ValueError):
        catalogue.scan_bounds("FVE-2026-02", "PHOTO", date(2026, 9, 1), date(2026, 6, 1))


def test_prefix_for_drawings():
    assert catalogue.prefix("FVE-2026-02", "DRAWING") == b"FVE-2026-02#DRAWING#"
    assert catalogue.prefix("FVE-2026-02") == b"FVE-2026-02#"
    ts = datetime(2026, 2, 25, 12, 0, 0)
    drawing = catalogue.row_key("FVE-2026-02", "DRAWING", ts, FILE_ID)
    assert drawing.startswith(catalogue.prefix("FVE-2026-02", "DRAWING"))
    assert not catalogue.row_key("FVE-2026-02", "DOC", ts, FILE_ID).startswith(
        catalogue.prefix("FVE-2026-02", "DRAWING")
    )
    assert not catalogue.row_key("FVE-2026-03", "DRAWING", ts, FILE_ID).startswith(
        catalogue.prefix("FVE-2026-02", "DRAWING")
    )
    with pytest.raises(ValueError):
        catalogue.prefix("FVE-2026-02", "DRAWINGS")


def test_cells_write_the_documented_formats():
    cells = catalogue.cells(
        {
            "meta": {"lat": 49.331, "lon": 14.165, "taken_at": datetime(2026, 4, 15, 9, 30), "device": None},
            "doc": {"is_final": True, "file_date": date(2026, 2, 25)},
        }
    )
    assert cells == {
        b"meta:lat": b"49.331000",
        b"meta:lon": b"14.165000",
        b"meta:taken_at": b"2026-04-15 09:30:00",
        b"doc:is_final": b"true",
        b"doc:file_date": b"2026-02-25",
    }


def test_sample_rows_use_the_contract_values():
    rows = sample_rows()
    kinds = {}
    for key, cells in rows.items():
        project, kind, ts, _ = key.decode().split("#")
        kinds.setdefault(kind, []).append((project, ts, cells))
    assert {kind: len(found) for kind, found in kinds.items()} == {
        "PHOTO": 11,
        "VIDEO": 1,
        "DOC": 3,
        "DRAWING": 3,
    }

    # Files that only have a date are keyed at 00:00:00 of that date (contracts section 8).
    for kind in ("VIDEO", "DOC", "DRAWING"):
        assert all(ts.endswith("000000") for _, ts, _ in kinds[kind])
    assert [ts for _, ts, _ in kinds["VIDEO"]] == ["20260520000000"]

    # filing_rule and doc_type are the values Task 19 writes (contracts section 6).
    for project, _, cells in kinds["PHOTO"]:
        expected = b"NONE" if project == config.UNASSIGNED else b"GPS"
        assert cells[b"meta:filing_rule"] == expected
    assert [cells[b"meta:filing_rule"] for _, _, cells in kinds["VIDEO"]] == [b"FOLDER"]
    assert sorted(cells[b"doc:doc_type"] for _, _, cells in kinds["DOC"]) == [b"CONTRACT", b"GRID", b"PERMIT"]
    assert {cells[b"doc:doc_type"] for _, _, cells in kinds["DRAWING"]} == {b"DRAWING"}

    # Coordinates with 6 decimals.
    first = next(cells for _, ts, cells in kinds["PHOTO"] if ts == "20260415093000")
    assert (first[b"meta:lat"], first[b"meta:lon"]) == (b"49.332078", b"14.165000")


@pytest.mark.skipif(
    not _hbase_reachable(),
    reason=f"HBase Thrift {config.HBASE_HOST}:{config.HBASE_PORT} not reachable: start the stack with "
    "--profile hbase and run the tests in the client container",
)
def test_sample_rows_roundtrip(monkeypatch):
    rows = sample_rows()
    assert len(rows) == 18
    filed = [k for k in rows if k.split(b"#")[1] == b"PHOTO" and not k.startswith(b"UNASSIGNED#")]
    assert len(filed) == len(FILED_TO)

    # A table of its own, so the test never touches media_catalog.
    monkeypatch.setattr(config, "HBASE_TABLE", f"{config.HBASE_TABLE}_test_{uuid.uuid4().hex[:8]}")
    conn = catalogue.connect()
    try:
        assert catalogue.create_table(conn) is True
        assert catalogue.create_table(conn) is False
        assert put_rows(conn, rows) == 18
        table = conn.table(config.HBASE_TABLE)
        assert dict(table.scan()) == rows

        # "Photos of FVE-2026-02 from 15 Apr to 20 May 2026": one range scan, in time order, end day included.
        start, stop = catalogue.scan_bounds("FVE-2026-02", "PHOTO", date(2026, 4, 15), date(2026, 5, 20))
        found = [d[b"meta:original_name"].decode() for _, d in table.scan(row_start=start, row_stop=stop)]
        assert found == ["IMG_20260415_093000_00001.jpg", "IMG_20260520_101500_00001.jpg"]

        # "The latest drawing of FVE-2026-02": one prefix scan; the last row is the newest.
        drawings = list(table.scan(row_prefix=catalogue.prefix("FVE-2026-02", "DRAWING")))
        assert [d[b"doc:version"] for _, d in drawings] == [b"v1", b"v2", b"final"]
        assert drawings[-1][1][b"doc:is_final"] == b"true"

        thumb = rows[filed[0]][catalogue.THUMB_COLUMN]
        assert thumb[:2] == b"\xff\xd8"
        assert Image.open(io.BytesIO(thumb)).size == catalogue.THUMB_SIZE
    finally:
        if config.HBASE_TABLE.encode() in conn.tables():
            conn.delete_table(config.HBASE_TABLE, disable=True)
        conn.close()
