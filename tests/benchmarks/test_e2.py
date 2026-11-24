"""Unit tests for experiment E2's helpers (benchmarks/e2): parsing the NameNode and hdfs outputs, the summary
table and the safety rule for deleting. The experiment itself needs the stack."""

from __future__ import annotations

import pytest

from benchmarks.e2 import namenode_stats as nn
from benchmarks.e2 import run_e2

JMX = {
    "beans": [
        {"name": "Hadoop:service=NameNode,name=FSNamesystem", "FilesTotal": 584012, "BlocksTotal": 291840},
        {"name": "Hadoop:service=NameNode,name=JvmMetrics", "MemHeapUsedM": 212.5},
        {"name": "java.lang:type=Memory"},
    ]
}

FSCK = """Connecting to namenode via http://namenode:9870/fsck?ugi=root&path=%2Fbench%2Fx10%2Floose
FSCK started by root (auth:SIMPLE) from /172.18.0.5 for path /bench/x10/loose at Thu Nov 19 10:00:00 UTC 2026

Status: HEALTHY
 Number of data-nodes:\t1
 Number of racks:\t\t1
 Total dirs:\t\t\t2
 Total symlinks:\t\t0

Replicated Blocks:
 Total size:\t2350839123 B
 Total files:\t291840
 Total blocks (validated):\t291840 (avg. block size 8055 B)
 Minimally replicated blocks:\t291840 (100.0 %)

The filesystem under path '/bench/x10/loose' is HEALTHY
"""


def test_parse_jmx():
    assert nn.parse_jmx(JMX) == {"files_total": 584012, "blocks_total": 291840, "heap_mb": 212.5}
    with pytest.raises(ValueError, match="without"):
        nn.parse_jmx({"beans": JMX["beans"][:1]})


def test_parse_count():
    out = "           2       291840         2350839123 /bench/x10/loose\n"
    assert nn.parse_count(out) == {"dirs": 2, "files": 291840, "bytes": 2350839123}
    with pytest.raises(ValueError):
        nn.parse_count("count: `/nope': No such file or directory")


def test_parse_fsck():
    assert nn.parse_fsck(FSCK) == {
        "files": 291840,
        "dirs": 2,
        "blocks": 291840,
        "bytes": 2350839123,
        "healthy": True,
    }


def test_objects_and_estimate():
    stats = {"files": 291840, "dirs": 2, "blocks": 291840}
    assert nn.objects(stats) == 583682
    assert nn.estimated_mb(stats) == pytest.approx(87.55, abs=0.01)


def test_only_bench_paths_are_deleted():
    for ok in ("/bench/x10/loose", "/bench/x10/lake", "/bench/main/lake"):
        run_e2.check_deletable(ok)
    for bad in ("/lake", "/lake/raw/photos", "/bench", "/bench/", "/bench/../lake", "hdfs:///bench/x10", "/"):
        with pytest.raises(ValueError, match="refusing"):
            run_e2.check_deletable(bad)


def test_dry_run_uses_its_own_lake(monkeypatch):
    from common import config

    for name in ("LAKE_ROOT", "LAKE_RAW", "LAKE_CLEAN", "LAKE_DW", "CLEAN_DB"):
        monkeypatch.setattr(config, name, getattr(config, name))
    run_e2.use_bench_lake("main")
    assert (config.LAKE_ROOT, config.LAKE_RAW) == ("/bench/main/lake", "/bench/main/lake/raw")
    assert config.CLEAN_DB == "fve_bench_main"
    assert run_e2.results_path("main").name == "results_main.csv"
    assert run_e2.results_path("x10").name == "results.csv"


def _rows():
    rows = []
    for run in (1, 2, 3):
        rows.append(
            {"variant": "loose", "run": str(run), "files": "291840", "blocks": "291840", "dirs": "2",
             "heap_mb": str(200 + run), "seconds": str(1000 + run), "read_100_seconds": "1.5"}
        )  # fmt: skip
        rows.append(
            {"variant": "packed", "run": str(run), "files": "3900", "blocks": "3900", "dirs": "140",
             "heap_mb": str(60 + run), "seconds": str(400 + run), "read_100_seconds": "45.0"}
        )  # fmt: skip
    return rows


def test_summary_and_table():
    summary = run_e2.summarize(_rows())
    assert summary["loose"]["objects"] == 583682 and summary["packed"]["objects"] == 7940
    assert summary["loose"]["seconds"] == 1002 and summary["packed"]["heap_mb"] == 62
    table = run_e2.results_table(summary)
    assert "| loose | 291,840 | 2 | 291,840 | 583,682 |" in table
    assert "Packed objects are 1.36% of the loose objects" in table
    assert "Medians of 3 runs" in table


def test_update_readme_replaces_only_the_results(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(f"# E2\n\nintro\n\n{run_e2.BEGIN}\nold\n{run_e2.END}\n\nafter\n", encoding="utf-8")
    run_e2.update_readme("| new |", readme)
    assert readme.read_text(encoding="utf-8") == (
        f"# E2\n\nintro\n\n{run_e2.BEGIN}\n| new |\n{run_e2.END}\n\nafter\n"
    )
    readme.write_text("no markers", encoding="utf-8")
    with pytest.raises(ValueError):
        run_e2.update_readme("x", readme)
