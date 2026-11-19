"""Experiment E5 (benchmarks/e5): query loading, fingerprints, results.csv and its checks; no stack needed."""

from __future__ import annotations

from decimal import Decimal

import pytest

from benchmarks.e5 import compare_results, run_e5, run_partition
from warehouse.sql import render


def _row(query, engine, run, seconds, fingerprint="f", rows="3"):
    return {
        "query": query,
        "engine": engine,
        "run": str(run),
        "seconds": str(seconds),
        "rows": rows,
        "fingerprint": fingerprint,
    }


def _full(fingerprint="f"):
    rows = []
    for engine, base in (("hive", 100.0), ("spark", 2.0)):
        for query in (*run_e5.QUERY_FILES, *compare_results.PARTITION_QUERIES):
            fp = "p" if query.startswith("partition") else f"{query}-{fingerprint}"
            rows += [_row(query, engine, run, base * run, fp) for run in (1, 2, 3)]
    return rows


def test_load_queries_renders_the_database():
    queries = run_e5.load_queries("fve_dw_x10")
    assert list(queries) == ["q1", "q3", "q4", "q5", "v1"]
    for sql in queries.values():
        assert "fve_dw_x10." in sql and "${" not in sql


def test_fingerprint_ignores_row_order_but_not_values():
    rows = [(1, Decimal("2.50"), None), (2, Decimal("1.00"), "x")]
    assert run_e5.result_fingerprint(rows) == run_e5.result_fingerprint(rows[::-1])
    # Hive and Spark both return Decimal through pyhive; the text form is what is compared
    assert run_e5.result_fingerprint([(1, Decimal("2.50"))]) == run_e5.result_fingerprint([("1", "2.50")])
    assert run_e5.result_fingerprint([(1, Decimal("2.50"))]) != run_e5.result_fingerprint(
        [(1, Decimal("2.5"))]
    )


def test_write_results_replaces_only_the_rerun_engine(tmp_path):
    path = tmp_path / "results.csv"
    run_e5.write_results([_row("q1", "spark", r, 1.0) for r in (1, 2, 3)], path)
    run_e5.write_results([_row("q1", "hive", r, 9.0) for r in (1, 2, 3)], path)
    rows = run_e5.write_results([_row("q1", "hive", r, 5.0) for r in (1, 2, 3)], path)  # Hive rerun
    assert len(rows) == 6
    assert [(r["engine"], r["seconds"]) for r in run_e5.read_results(path)] == [("hive", "5.0")] * 3 + [
        ("spark", "1.0")
    ] * 3


def test_cold_and_warm_is_run_1_and_the_median_of_the_rest():
    rows = [_row("q1", "hive", 1, 1053.6), _row("q1", "hive", 2, 310.3), _row("q1", "hive", 3, 317.0)]
    cold, warm = run_e5.cold_and_warm(rows, "q1", "hive")
    assert cold == 1053.6 and warm == pytest.approx(313.65)  # not the mean of all three (560.3)
    with pytest.raises(ValueError):
        run_e5.cold_and_warm(rows[:1], "q1", "hive")


def test_checks_pass_on_equal_results_and_fail_on_a_difference():
    rows = _full()
    assert all(passed for _, passed, _ in compare_results.checks(rows))
    rows[0]["fingerprint"] = "other"  # one Hive run of q1 differs
    failed = {name for name, passed, _ in compare_results.checks(rows) if not passed}
    assert failed == {"q1"}


def test_checks_fail_when_the_flat_copy_differs():
    rows = [
        r if r["query"] != "partition_no" or r["engine"] != "hive" else {**r, "fingerprint": "q"}
        for r in _full()
    ]
    failed = {name for name, passed, _ in compare_results.checks(rows) if not passed}
    assert failed == {"partition"}


def test_table_skips_queries_without_warm_runs():
    rows = [r for r in _full() if not (r["query"] == "partition_no" and r["run"] != "1")]
    table = {t[0]: t for t in compare_results.table(rows)}
    assert "partition_no" not in table and "partition_yes" in table
    assert table["q1"][1:] == (100.0, 2.0, 250.0, 5.0, 50.0)


def test_partition_sql_drops_its_copy_at_the_end():
    statements = render(run_partition.SQL_FILE, DW_DB="fve_dw_x10")
    assert len(statements) == len(run_partition.LABELS)
    assert statements[1].upper().startswith("CREATE TABLE FVE_DW_X10.FACT_INVOICE_LINE_FLAT")
    assert statements[-1].upper().startswith("DROP TABLE IF EXISTS FVE_DW_X10.FACT_INVOICE_LINE_FLAT")


def test_committed_results_are_complete():
    """Task 31.1's Verify: 5 queries x 2 engines x 3 runs + the partition rows; same results on both."""
    rows = run_e5.read_results()
    main = [r for r in rows if r["query"] in run_e5.QUERY_FILES]
    assert len(main) == 5 * 2 * 3
    assert {r["query"] for r in rows} - set(run_e5.QUERY_FILES) == set(compare_results.PARTITION_QUERIES)
    assert all(passed for _, passed, _ in compare_results.checks(rows))
