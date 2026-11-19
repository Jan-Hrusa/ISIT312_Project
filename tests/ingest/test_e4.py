"""Experiment E4 (benchmarks/e4/run_e4.py): queries, monthly rows and daily summaries, without the stack."""

from __future__ import annotations

import csv
from datetime import date, datetime

import pytest

from benchmarks.e4 import run_e4

START, END = date(2026, 1, 30), date(2026, 3, 2)  # 32 days over three months


def _monthly(source, year, month, files, size):
    return {"source": source, "arrival_year": year, "arrival_month": month, "files": files, "bytes": size}


def test_load_queries_renders_database_and_period():
    queries = run_e4.load_queries(START, END)
    assert set(run_e4.QUERIES) <= set(queries)
    for sql in queries.values():
        assert "${" not in sql
        assert "DATE '2026-01-30' AND DATE '2026-03-02'" in sql
        assert ".ingest_log" in sql


def test_months_cross_the_year_end():
    assert run_e4.months(date(2025, 11, 15), date(2026, 2, 1)) == [
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
    ]


def test_monthly_results_has_every_source_and_month():
    rows = run_e4.monthly_results(
        [_monthly("kpc", 2026, 2, 3, 369), _monthly("photos", 2026, 1, 1, 7_500)],
        ["kpc", "photos"],
        START,
        END,
    )
    assert len(rows) == 2 * 3  # one row per source and month, months without a file included
    kpc = {(r["year"], r["month"]): r for r in rows if r["source"] == "kpc"}
    assert (kpc[(2026, 1)]["files"], kpc[(2026, 2)]["files"], kpc[(2026, 3)]["files"]) == (0, 3, 0)
    assert kpc[(2026, 2)]["mb"] == 0.000369  # small sources don't round to 0.0


def test_daily_summaries_count_days_without_files():
    monthly = run_e4.monthly_results(
        [_monthly("kpc", 2026, 2, 3, 300), _monthly("photos", 2026, 2, 10, 1_000_000)],
        ["kpc", "photos"],
        START,
        END,
    )
    daily = [
        {"source": "kpc", "business_date": date(2026, 2, 3), "files": 2},
        {
            "source": "kpc",
            "business_date": datetime(2026, 2, 4, 0, 0),
            "files": 1,
        },  # Spark may give datetimes
        {"source": "photos", "business_date": date(2026, 2, 3), "files": 10},
    ]
    summary = {s["source"]: s for s in run_e4.daily_summaries(daily, monthly, ["kpc", "photos"], START, END)}
    kpc = summary["kpc"]
    assert (kpc["files"], kpc["peak_day_files"], kpc["peak_day_date"]) == (3, 2, "2026-02-03")
    assert (kpc["median_daily_files"], kpc["no_file_days"]) == (0, 30)
    assert kpc["no_file_days_pct"] == pytest.approx(93.8)
    everything = summary[run_e4.ALL_SOURCES]
    assert (everything["files"], everything["peak_day_files"], everything["no_file_days"]) == (13, 12, 30)
    assert everything["files_per_day"] == round(13 / 32, 2)


def test_check_totals_rejects_a_difference():
    summary = [{"source": "kpc", "files": 3}, {"source": run_e4.ALL_SOURCES, "files": 3}]
    run_e4.check_totals(summary, [{"source": "kpc", "files": 3}])
    with pytest.raises(RuntimeError):
        run_e4.check_totals(summary, [{"source": "kpc", "files": 4}])


def test_committed_results_one_row_per_source_and_month():
    """Task 27.1's Verify: results.csv has one row per source and month of the data period."""
    with run_e4.RESULTS_FILE.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    keys = [(r["source"], int(r["year"]), int(r["month"])) for r in rows]
    sources = {k[0] for k in keys}
    assert (
        len(keys)
        == len(set(keys))
        == len(sources) * len(run_e4.months(run_e4.config.DATA_START, run_e4.config.DATA_END))
    )
    with run_e4.SUMMARY_FILE.open(encoding="utf-8") as f:
        summary = {r["source"]: r for r in csv.DictReader(f)}
    assert set(summary) == sources | {run_e4.ALL_SOURCES}
    for source in sources:
        assert int(summary[source]["files"]) == sum(int(r["files"]) for r in rows if r["source"] == source)
