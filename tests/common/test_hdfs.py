"""Tests for common/hdfs.py on the local file system (the tests' `file://` lake folder).

The snapshot helpers need a real HDFS (HdfsAdmin): they are checked on the Docker stack, and Task 14's tests
monkeypatch them.
"""

from __future__ import annotations

import pytest

from common import hdfs


def test_put_copies_bytes_and_creates_parent_folders(spark, tmp_path):
    local = tmp_path / "statement.gpc"
    local.write_bytes(b"074 statement\r\n075 transaction\r\n")
    target = (
        tmp_path / "lake" / "raw" / "bank_gpc" / "2026" / "01" / "statement__20261114093000.gpc"
    ).as_uri()

    assert not hdfs.exists(spark, target)
    hdfs.put(spark, str(local), target)

    assert hdfs.exists(spark, target)
    assert hdfs.read_bytes(spark, target) == local.read_bytes()
    assert local.exists()


def test_put_refuses_an_existing_target(spark, tmp_path):
    local = tmp_path / "a.txt"
    local.write_bytes(b"new")
    target_file = tmp_path / "raw" / "a.txt"
    target_file.parent.mkdir()
    target_file.write_bytes(b"old")

    with pytest.raises(FileExistsError, match="write-once"):
        hdfs.put(spark, str(local), target_file.as_uri())
    assert target_file.read_bytes() == b"old"


def test_mkdirs_and_ls(spark, tmp_path):
    folder = tmp_path / "lake" / "raw"
    hdfs.mkdirs(spark, (folder / "kpc").as_uri())
    hdfs.mkdirs(spark, (folder / "kpc").as_uri())
    (folder / "b.txt").write_bytes(b"b")
    (folder / "a.txt").write_bytes(b"a")

    assert all(entry.startswith("file:") for entry in hdfs.ls(spark, folder.as_uri()))
    assert [entry.rsplit("/", 1)[1] for entry in hdfs.ls(spark, folder.as_uri())] == ["a.txt", "b.txt", "kpc"]
    # A path without a scheme (the stack's raw paths) comes back without one.
    assert hdfs.ls(spark, str(folder)) == [
        f"{folder.as_posix()}/{name}" for name in ("a.txt", "b.txt", "kpc")
    ]


def test_fs_is_the_default_file_system(spark):
    assert str(hdfs.fs(spark).getUri().toString()) == "file:///"
