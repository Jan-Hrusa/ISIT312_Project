"""Task 17: statistics and scaling."""

from __future__ import annotations

import os
import random
from datetime import datetime, timezone

import pytest

from common import config
from generators import scale
from generators.finance_docs import plan


def _plan(scale_: int) -> tuple[list, list, list]:
    projects, _, _, invoices = plan.build_plan(random.Random(config.SEED), scale_)
    signed = [p for p in projects if p["status"] != "NOT_SIGNED"]
    return projects, signed, invoices


def test_scale_multiplies_invoices():
    # The total doesn't double exactly: each year draws 8 or 9 offers (x scale) and about 10% stay unsigned
    # (seed 312: 1.90x at scale 2). Doubled are the offers per year; each signed project keeps its invoices.
    years = config.DATA_END.year - config.DATA_START.year + 1
    projects_1, signed_1, invoices_1 = _plan(1)
    projects_2, signed_2, invoices_2 = _plan(2)
    assert 8 * years <= len(projects_1) <= 9 * years
    assert 16 * years <= len(projects_2) <= 18 * years
    per_project_1 = len(invoices_1) / len(signed_1)
    per_project_2 = len(invoices_2) / len(signed_2)
    assert abs(per_project_2 - per_project_1) <= 0.05 * per_project_1


def test_stats_file_lists_every_type(tmp_path):
    src = tmp_path / "sources"
    src.mkdir()
    stamp = datetime(2024, 5, 1, 12, tzinfo=timezone.utc).timestamp()
    for ext in scale.TYPES:
        f = src / f"a{ext}"
        f.write_bytes(b"x" * 10)
        os.utime(f, (stamp, stamp))
    text = scale.render_stats(src, tmp_path / "ledger")
    for label in scale.ORDER:
        assert f"| {label} |" in text
    assert "| 2024 |" in text


def test_write_section_keeps_the_other_section(tmp_path):
    doc = tmp_path / "d.md"
    scale.write_section(doc, scale.STATS_MARK, "Scale 1", "one\n")
    scale.write_section(doc, scale.X10_MARK, "Scaled dataset (x10)", "ten\n")
    scale.write_section(doc, scale.STATS_MARK, "Scale 1", "one again\n")
    text = doc.read_text()
    assert "one again\n<!-- stats:end -->\n\n<!-- x10:begin -->" in text
    assert text.count("<!-- x10:begin -->") == 1 and "ten\n<!-- x10:end -->\n" in text
    assert text.endswith("<!-- x10:end -->\n")


def _fake_generators(monkeypatch, sources, out):
    """Replace the generator subprocesses by a function that writes one file per generator."""
    calls = []

    def fake(module, scale_, seed, env, cwd):
        calls.append((module, scale_, seed, env["FVE_DATASET"]))
        (sources / module).mkdir(parents=True, exist_ok=True)
        (sources / module / "data.csv").write_text(module)
        (out / "ledger").mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(scale, "run_generator", fake)
    return calls


def test_scale_runs_generators_in_order(tmp_path, monkeypatch):
    sources, out = tmp_path / "sources_x10", tmp_path / "out_x10"
    calls = _fake_generators(monkeypatch, sources, out)
    doc, manifest = tmp_path / "d.md", tmp_path / "m.sha256"
    kwargs = {"root": tmp_path, "sources": sources, "out": out, "doc": doc, "manifest": manifest}
    assert scale.run_scale(10, record=True, **kwargs)
    assert calls == [
        ("generators.finance_docs", 10, 312, "x10"),
        ("generators.bank", 10, 312, "x10"),
        ("generators.media", 10, 312, "x10"),
    ]
    assert "Scaled dataset (x10)" in doc.read_text()
    assert len(manifest.read_text().splitlines()) == 3

    # A second run refuses to write over the first run's files; only scale 10 exists.
    with pytest.raises(SystemExit, match="not empty"):
        scale.run_scale(10, **kwargs)
    with pytest.raises(ValueError):
        scale.run_scale(2, **kwargs)


def test_check_finds_a_changed_file(tmp_path, monkeypatch, capsys):
    sources, out = tmp_path / "sources_x10", tmp_path / "out_x10"
    _fake_generators(monkeypatch, sources, out)
    kwargs = {"root": tmp_path, "sources": sources, "out": out, "manifest": tmp_path / "m.sha256"}
    scale.run_scale(10, record=True, doc=tmp_path / "d.md", **kwargs)
    assert scale.check(**kwargs)
    assert "OK" in capsys.readouterr().out

    (sources / "generators.bank" / "data.csv").write_text("changed")
    (sources / "extra.txt").write_text("x")
    assert not scale.check(**kwargs)
    printed = capsys.readouterr().out
    assert "different: sources_x10/generators.bank/data.csv" in printed
    assert "extra:     sources_x10/extra.txt" in printed
