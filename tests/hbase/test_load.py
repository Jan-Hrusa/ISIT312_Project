"""Loading the media tables into the HBase catalogue (Task 19)."""

from __future__ import annotations

import socket
import uuid
from collections import Counter

import pytest

from common import config, tables
from hbase import catalogue, load
from hbase.sample_rows import sample_rows
from processing.media import run as run_media
from tests.processing.test_media import media_inputs, write_projects


def _hbase_reachable() -> bool:
    try:
        with socket.create_connection((config.HBASE_HOST, config.HBASE_PORT), timeout=2):
            return True
    except OSError:
        return False


def test_original_name_from_raw_path():
    assert load._original_name("/lake/raw/docs/FVE-2026-02/2026/02/site_layout_v2__20261114120000.dwg") == (
        "site_layout_v2.dwg"
    )
    assert load._original_name("/tmp/sources/drive/projects/FVE-2026-02/contract.docx") == "contract.docx"


@pytest.mark.skipif(
    not _hbase_reachable(),
    reason=f"HBase Thrift {config.HBASE_HOST}:{config.HBASE_PORT} not reachable: start the stack with "
    "--profile hbase and run the tests in the client container",
)
def test_load_counts_match(clean_db, sources_tree, tmp_path, monkeypatch):
    """The Validate step on the samples: prefix counts per project and kind equal the clean tables, and every
    row matches the Task 12 sample rows apart from the raw paths."""
    write_projects(clean_db, sources_tree)
    run_media(clean_db, media_inputs(clean_db, sources_tree, tmp_path))
    monkeypatch.setattr(config, "HBASE_TABLE", f"{config.HBASE_TABLE}_test_{uuid.uuid4().hex[:8]}")
    conn = catalogue.connect()
    try:
        assert load.run(clean_db) == {"rows": 18}
        table = conn.table(config.HBASE_TABLE)
        loaded = dict(table.scan())

        media = tables.read_table(clean_db, "media_files").collect()
        docs = tables.read_table(clean_db, "documents").collect()
        for project in {r.project_code for r in media} | {r.project_code for r in docs}:
            kinds = Counter(
                k.split(b"#")[1].decode() for k, _ in table.scan(row_prefix=catalogue.prefix(project))
            )
            assert kinds["PHOTO"] + kinds["VIDEO"] == sum(r.project_code == project for r in media), project
            assert kinds["DOC"] + kinds["DRAWING"] == sum(r.project_code == project for r in docs), project

        expected = sample_rows()
        assert set(loaded) == set(expected)
        for key, cells in expected.items():
            without_loc = {c: v for c, v in cells.items() if not c.startswith(b"loc:")}
            assert {c: v for c, v in loaded[key].items() if not c.startswith(b"loc:")} == without_loc, key
            if b"loc:seq_key" in cells:
                assert loaded[key][b"loc:seq_key"] == cells[b"loc:seq_key"]
    finally:
        if config.HBASE_TABLE.encode() in conn.tables():
            conn.delete_table(config.HBASE_TABLE, disable=True)
        conn.close()
