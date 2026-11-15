"""Task 17: statistics and scaling."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from generators import scale
from generators.finance_docs import __main__ as finance_docs


def test_scale_multiplies_invoices(tmp_path):
    one = finance_docs.generate(312, 1, tmp_path / "s1", tmp_path / "l1")
    two = finance_docs.generate(312, 2, tmp_path / "s2", tmp_path / "l2")
    assert abs(two["invoices"] - 2 * one["invoices"]) <= 0.10 * 2 * one["invoices"]


def test_stats_file_lists_every_type(tmp_path):
    src = tmp_path / "sources"
    src.mkdir()
    stamp = datetime(2024, 5, 1, 12, tzinfo=UTC).timestamp()
    for ext in scale.TYPES:
        f = src / f"a{ext}"
        f.write_bytes(b"x" * 10)
        os.utime(f, (stamp, stamp))
    text = scale.render_stats(src, tmp_path / "ledger")
    for label in scale.ORDER:
        assert f"| {label} |" in text
    assert "| 2024 |" in text


def test_scale_runs_generators_in_order(tmp_path, monkeypatch):
    calls = []

    def fake(module, scale_, seed, env, cwd):
        calls.append((module, scale_, seed, env["FVE_DATASET"]))

    monkeypatch.setattr(scale, "run_generator", fake)
    scale.run_scale(10, doc=tmp_path / "d.md", manifest=tmp_path / "m.sha256", root=tmp_path)
    assert calls == [
        ("generators.finance_docs", 10, 312, "x10"),
        ("generators.bank", 10, 312, "x10"),
        ("generators.media", 10, 312, "x10"),
    ]
    assert "Scaled dataset (x10)" in (tmp_path / "d.md").read_text()
