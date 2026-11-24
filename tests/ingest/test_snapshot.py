"""Tests for raw-zone HDFS snapshots."""

from __future__ import annotations

import pytest

import ingest
from common import config
from ingest import restore_demo, snapshot


def test_snapshot_created_after_run(monkeypatch):
    calls = []

    def fake_collect(spark, **kwargs):
        calls.append("collect")
        return {
            "master": {"new": 3, "skipped": 2},
            "kpc": {"new": 4, "skipped": 1},
        }

    monkeypatch.setattr("ingest.collect.collect", fake_collect)
    monkeypatch.setattr(snapshot.config, "DATASET", "main")
    monkeypatch.setattr(
        snapshot,
        "ensure_snapshottable",
        lambda spark: calls.append("ensure"),
    )
    monkeypatch.setattr(
        snapshot,
        "take",
        lambda spark, run_id: calls.append(("take", run_id)) or "/lake/raw/.snapshot/raw-test",
    )
    monkeypatch.setattr(
        snapshot,
        "prune",
        lambda spark: calls.append("prune"),
    )

    result = ingest.run(object())

    assert result["files_new"] == 7
    assert result["files_skipped"] == 3
    assert result["snapshot"] == 1
    assert [call if isinstance(call, str) else call[0] for call in calls] == [
        "collect",
        "ensure",
        "take",
        "prune",
    ]
    assert calls[2][1].isdigit()
    assert len(calls[2][1]) == 14


def test_prune_keeps_30(monkeypatch):
    names = [f"raw-202611{i:02d}000000" for i in range(1, 36)]
    deleted = []

    monkeypatch.setattr(snapshot.hdfs, "list_snapshots", lambda spark, path: names)
    monkeypatch.setattr(
        snapshot.hdfs,
        "delete_snapshot",
        lambda spark, path, name: deleted.append(name),
    )

    snapshot.prune(object(), keep=30)

    assert deleted == names[:5]
    assert len(names) - len(deleted) == 30


def test_no_snapshot_for_x10(monkeypatch):
    calls = []

    def fake_collect(spark, **kwargs):
        return {"master": {"new": 1, "skipped": 0}}

    monkeypatch.setattr("ingest.collect.collect", fake_collect)
    monkeypatch.setattr(snapshot.config, "DATASET", "x10")
    monkeypatch.setattr(
        snapshot,
        "ensure_snapshottable",
        lambda spark: calls.append("ensure"),
    )
    monkeypatch.setattr(
        snapshot,
        "take",
        lambda spark, run_id: calls.append("take"),
    )
    monkeypatch.setattr(
        snapshot,
        "prune",
        lambda spark: calls.append("prune"),
    )

    result = ingest.run(object())

    assert result["snapshot"] == 0
    assert calls == []


def test_take_names_snapshot_after_run_id(monkeypatch):
    created = []
    monkeypatch.setattr(snapshot.config, "DATASET", "main")
    monkeypatch.setattr(snapshot.config, "LAKE_RAW", "/lake/raw")
    monkeypatch.setattr(
        snapshot.hdfs,
        "create_snapshot",
        lambda spark, path, name: created.append((path, name)) or f"{path}/.snapshot/{name}",
    )

    assert snapshot.take(object(), "20261117120000") == "/lake/raw/.snapshot/raw-20261117120000"
    assert created == [("/lake/raw", "raw-20261117120000")]


def test_take_skips_x10(monkeypatch):
    def no_hdfs(*args):
        raise AssertionError("no snapshot may be created for the x10 dataset")

    monkeypatch.setattr(snapshot.config, "DATASET", "x10")
    monkeypatch.setattr(snapshot.hdfs, "create_snapshot", no_hdfs)

    assert snapshot.take(object(), "20261117120000") == ""


# Restore demo: a fake raw zone (live project folder + snapshots), HDFS commands recorded instead of run.
PROJECT = "FVE-2016-01"
LIVE = {
    "2016/03/contract__20261116081000.docx": "MD5-a",
    "2016/04/site_layout_v1__20261116081000.dwg": "MD5-b",
}


def _fake_lake(monkeypatch, snapshots):
    """`snapshots`: {name: the project folder's files in that snapshot, or None when it isn't there}."""
    monkeypatch.setattr(config, "LAKE_RAW", "/lake/raw")
    project_dir = f"/lake/raw/docs/{PROJECT}"
    state = {"live": dict(LIVE)}
    commands = []

    def snapshot_name(path):
        return path.split("/.snapshot/")[1].split("/")[0]

    def listing(spark, root):
        if root == project_dir:
            return dict(state["live"] or {})
        return dict(snapshots[snapshot_name(root)])

    def exists(spark, path):
        if path == project_dir:
            return state["live"] is not None
        return snapshots.get(snapshot_name(path)) is not None

    def hadoop(*args):
        commands.append(args[0])
        if args[0] == "-rm":
            state["live"] = None
        elif args[0] == "-cp":
            state["live"] = dict(snapshots[snapshot_name(args[1])])

    monkeypatch.setattr(restore_demo, "_files_with_checksums", listing)
    monkeypatch.setattr(restore_demo.hdfs, "exists", exists)
    monkeypatch.setattr(restore_demo.hdfs, "list_snapshots", lambda spark, path: sorted(snapshots))
    monkeypatch.setattr(restore_demo, "_hadoop", hadoop)
    return state, commands


def test_restore_demo_restores_from_newest_snapshot(monkeypatch, capsys):
    older = {"2016/03/contract__20261116081000.docx": "MD5-a"}
    state, commands = _fake_lake(
        monkeypatch,
        {"raw-20261116081000": older, "raw-20261117120000": dict(LIVE), "other": dict(LIVE)},
    )

    assert restore_demo.restore(object(), PROJECT) == 2

    assert commands == ["-rm", "-cp"]
    assert state["live"] == LIVE
    out = capsys.readouterr().out
    assert "SNAPSHOT raw-20261117120000 matches the live folder" in out
    assert "MD5-b  2016/04/site_layout_v1__20261116081000.dwg" in out
    assert "RESTORED 2 files, checksums match" in out


def test_restore_demo_refuses_without_snapshot(monkeypatch):
    state, commands = _fake_lake(monkeypatch, {"raw-20261117120000": None})

    with pytest.raises(RuntimeError, match="Nothing was deleted"):
        restore_demo.restore(object(), PROJECT)

    assert commands == []
    assert state["live"] == LIVE


def test_restore_demo_refuses_when_snapshot_differs(monkeypatch):
    changed = dict(LIVE, **{"2016/04/site_layout_v1__20261116081000.dwg": "MD5-old"})
    state, commands = _fake_lake(monkeypatch, {"raw-20261117120000": changed})

    with pytest.raises(RuntimeError, match="Nothing was deleted"):
        restore_demo.restore(object(), PROJECT)

    assert commands == []
    assert state["live"] == LIVE
