"""E3's scaling point (benchmarks/e3/scale_q2.py): the CSV rows and the summary, without the stack."""

from __future__ import annotations

import pytest

from benchmarks.e3 import scale_q2


def _timings(hbase_seconds, hive_seconds, factor):
    result = {
        ("FVE-2026-02", "2026-06"): (146 * factor, 1_000_000 * factor),
        ("FVE-2026-03", "2026-07"): (4, 9),
    }
    return {"HBase": (hbase_seconds, result), "Hive": (hive_seconds, result)}


def test_result_rows_cold_runs_and_median():
    rows = scale_q2.result_rows(2, _timings([0.9, 0.3, 0.5, 0.4], [2.0, 1.1, 1.3, 1.2], 2))
    hbase = [r for r in rows if r["store"] == "HBase"]
    assert [r["run"] for r in hbase] == ["cold", "2", "3", "4", "median"]
    assert hbase[-1]["seconds"] == 0.4  # median of the warm runs only: the cold 0.9 is left out
    assert {(r["factor"], r["photos"], r["groups"]) for r in rows} == {(2, 296, 2)}


def test_summary_names_the_faster_store_per_factor():
    rows = scale_q2.result_rows(10, _timings([2.0, 1.9, 2.1], [1.6, 1.5, 1.4], 10))
    rows += scale_q2.result_rows(1, _timings([0.5, 0.3, 0.4], [1.6, 1.3, 1.2], 1))
    assert scale_q2.summary(rows) == [
        (1, 150, pytest.approx(0.35), pytest.approx(1.25), "HBase"),
        (10, 1464, pytest.approx(2.0), pytest.approx(1.45), "Hive"),
    ]


@pytest.mark.parametrize("factors, runs", [([1, 0], 10), ([1], 1)])
def test_run_rejects_bad_arguments(factors, runs):
    with pytest.raises(ValueError):
        scale_q2.run(factors, runs)
