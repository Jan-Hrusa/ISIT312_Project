"""Tests for raw-zone HDFS snapshots."""

from __future__ import annotations

import ingest
from ingest import snapshot


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
        snapshot, "ensure_snapshottable",
        lambda spark: calls.append("ensure"),
    )
    monkeypatch.setattr(
        snapshot, "take",
        lambda spark, run_id: calls.append(("take", run_id)) or "/lake/raw/.snapshot/raw-test",
    )
    monkeypatch.setattr(
        snapshot, "prune",
        lambda spark: calls.append("prune"),
    )

    result = ingest.run(object())

    assert result["files_new"] == 7
    assert result["files_skipped"] == 3
    assert result["snapshot"] == 1
    assert [call if isinstance(call, str) else call[0] for call in calls] == [
        "collect", "ensure", "take", "prune"
    ]
    assert calls[2][1].isdigit()
    assert len(calls[2][1]) == 14


def test_prune_keeps_30(monkeypatch):
    names = [f"raw-202611{i:02d}000000" for i in range(1, 36)]
    deleted = []

    monkeypatch.setattr(snapshot.hdfs, "list_snapshots", lambda spark, path: names)
    monkeypatch.setattr(
        snapshot.hdfs, "delete_snapshot",
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
        snapshot, "ensure_snapshottable",
        lambda spark: calls.append("ensure"),
    )
    monkeypatch.setattr(
        snapshot, "take",
        lambda spark, run_id: calls.append("take"),
    )
    monkeypatch.setattr(
        snapshot, "prune",
        lambda spark: calls.append("prune"),
    )

    result = ingest.run(object())

    assert result["snapshot"] == 0
    assert calls == []
