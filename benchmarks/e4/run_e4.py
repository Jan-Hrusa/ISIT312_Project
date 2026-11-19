"""Experiment E4: file arrival rates per source, measured from the collected-file log `ingest_log`.

Runs arrival_rates.sql with the project's Spark session and writes:
- results.csv: one row per source and month from config.DATA_START to DATA_END (months without a file = 0):
  source, year, month, files, bytes, mb;
- summary.csv: one row per source plus an `all sources` row: files, MB, files and MB per day, the peak day,
  the median day and the share of calendar days with no new file (days without a file count as 0).
It also checks the per-source totals against the SQL's own `source_totals` query and prints the summary.

    python -m benchmarks.e4.run_e4        # client container, profile core, after the collect step
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median

from common import config
from common.spark import get_spark
from warehouse.sql import named_queries

BASE_DIR = Path(__file__).resolve().parent
SQL_FILE = BASE_DIR / "arrival_rates.sql"
RESULTS_FILE = BASE_DIR / "results.csv"
SUMMARY_FILE = BASE_DIR / "summary.csv"
ALL_SOURCES = "all sources"
QUERIES = ("monthly_arrivals", "daily_arrivals", "source_totals")
RESULT_COLUMNS = ("source", "year", "month", "files", "bytes", "mb")
SUMMARY_COLUMNS = (
    "source",
    "files",
    "mb",
    "files_per_day",
    "mb_per_day",
    "peak_day_files",
    "peak_day_date",
    "median_daily_files",
    "no_file_days",
    "no_file_days_pct",
)


def load_queries(start: date = config.DATA_START, end: date = config.DATA_END) -> dict[str, str]:
    """The named queries of arrival_rates.sql rendered for the clean database and the data period."""
    queries = named_queries(SQL_FILE, DATA_START=start.isoformat(), DATA_END=end.isoformat())
    missing = set(QUERIES) - set(queries)
    if missing:
        raise ValueError(f"{SQL_FILE.name} lacks the named queries {sorted(missing)}")
    return queries


def months(start: date, end: date) -> list[tuple[int, int]]:
    """Every (year, month) from start to end, both included."""
    out, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        out.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def monthly_results(monthly_rows, sources, start: date, end: date) -> list[dict]:
    """results.csv rows: one per source and month, months without a file as 0."""
    data = {
        (r["source"], int(r["arrival_year"]), int(r["arrival_month"])): (
            int(r["files"]),
            int(r["bytes"] or 0),
        )
        for r in monthly_rows
    }
    rows = []
    for source in sources:
        for year, month in months(start, end):
            files, size = data.get((source, year, month), (0, 0))
            rows.append(
                {
                    "source": source,
                    "year": year,
                    "month": month,
                    "files": files,
                    "bytes": size,
                    "mb": round(size / 1_000_000, 6),
                }
            )
    return rows


def _day(value) -> date:
    return value.date() if isinstance(value, datetime) else value


def daily_summaries(daily_rows, monthly: list[dict], sources, start: date, end: date) -> list[dict]:
    """summary.csv rows: per source and for all sources together, over every calendar day of the period."""
    observed: dict[str, dict[date, int]] = defaultdict(dict)
    for r in daily_rows:
        observed[r["source"]][_day(r["business_date"])] = int(r["files"])
    observed[ALL_SOURCES] = defaultdict(int)
    for source in sources:
        for day, files in observed[source].items():
            observed[ALL_SOURCES][day] += files

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    out = []
    for source in [*sources, ALL_SOURCES]:
        counts = [observed[source].get(day, 0) for day in days]
        rows = monthly if source == ALL_SOURCES else [m for m in monthly if m["source"] == source]
        files, size = sum(m["files"] for m in rows), sum(m["bytes"] for m in rows)
        peak = max(counts)
        no_file_days = counts.count(0)
        out.append(
            {
                "source": source,
                "files": files,
                "mb": round(size / 1_000_000, 2),
                "files_per_day": round(files / len(days), 2),
                "mb_per_day": round(size / 1_000_000 / len(days), 4),
                "peak_day_files": peak,
                "peak_day_date": days[counts.index(peak)].isoformat(),
                "median_daily_files": median(counts),
                "no_file_days": no_file_days,
                "no_file_days_pct": round(no_file_days / len(days) * 100, 1),
            }
        )
    return out


def check_totals(summary: list[dict], totals_rows) -> None:
    """The per-source file counts must equal the SQL's `source_totals` (both read the same log)."""
    expected = {r["source"]: int(r["files"]) for r in totals_rows}
    got = {s["source"]: s["files"] for s in summary if s["source"] != ALL_SOURCES}
    if got != expected:
        raise RuntimeError(f"monthly totals {got} differ from source_totals {expected}")


def write_csv(path: Path, columns, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def run(start: date = config.DATA_START, end: date = config.DATA_END) -> list[dict]:
    queries = load_queries(start, end)
    spark = get_spark("e4")
    try:
        monthly_rows = spark.sql(queries["monthly_arrivals"]).collect()
        daily_rows = spark.sql(queries["daily_arrivals"]).collect()
        totals_rows = spark.sql(queries["source_totals"]).collect()
    finally:
        spark.stop()

    sources = sorted({r["source"] for r in monthly_rows})
    if not sources:
        raise RuntimeError(f"No rows in {config.CLEAN_DB}.ingest_log: run the collect step first (Task 14).")
    monthly = monthly_results(monthly_rows, sources, start, end)
    summary = daily_summaries(daily_rows, monthly, sources, start, end)
    check_totals(summary, totals_rows)
    write_csv(RESULTS_FILE, RESULT_COLUMNS, monthly)
    write_csv(SUMMARY_FILE, SUMMARY_COLUMNS, summary)

    print(f"written {RESULTS_FILE} ({len(monthly)} rows) and {SUMMARY_FILE}")
    print(
        f"{'source':<12} {'files':>7} {'MB':>8} {'files/day':>9} "
        f"{'peak':>5} {'median':>6} {'no-file days':>12}"
    )
    for s in summary:
        print(
            f"{s['source']:<12} {s['files']:>7} {s['mb']:>8.2f} {s['files_per_day']:>9.2f} "
            f"{s['peak_day_files']:>5} {s['median_daily_files']:>6} {s['no_file_days_pct']:>11.1f}%"
        )
    return summary


if __name__ == "__main__":
    run()
