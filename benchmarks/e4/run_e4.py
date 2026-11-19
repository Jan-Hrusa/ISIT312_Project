from __future__ import annotations

import csv
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median

from common import config
from common.spark import get_spark

BASE_DIR = Path(__file__).resolve().parent
SQL_FILE = BASE_DIR / "arrival_rates.sql"
RESULTS_FILE = BASE_DIR / "results.csv"


def load_queries() -> dict[str, str]:
    """Load the named SQL queries and insert project configuration values."""
    sql_text = SQL_FILE.read_text(encoding="utf-8")

    sections = re.split(r"(?m)^-- name:\s*(\w+)\s*$", sql_text)

    queries = {}
    for index in range(1, len(sections), 2):
        name = sections[index].strip()
        query = sections[index + 1].strip()

        query = query.replace("${CLEAN_DB}", config.CLEAN_DB)
        query = query.replace("${DATA_START}", config.DATA_START.isoformat())
        query = query.replace("${DATA_END}", config.DATA_END.isoformat())

        queries[name] = query

    required = {"monthly_arrivals", "daily_arrivals"}
    if not required.issubset(queries):
        raise ValueError("arrival_rates.sql must contain both named queries.")

    return queries


def build_daily_summaries(daily_rows, sources, start_date, end_date):
    """Calculate daily arrival statistics, including days with zero files."""
    observed = defaultdict(dict)

    for row in daily_rows:
        source = row["source"]
        business_date = row["business_date"]

        if isinstance(business_date, datetime):
            business_date = business_date.date()

        observed[source][business_date] = int(row["files"])

    summaries = {}

    for source in sources:
        counts = []
        current_date = start_date

        while current_date <= end_date:
            counts.append(observed[source].get(current_date, 0))
            current_date = date.fromordinal(current_date.toordinal() + 1)

        peak_count = max(counts)
        peak_index = counts.index(peak_count)
        peak_date = date.fromordinal(start_date.toordinal() + peak_index)

        no_file_days = sum(count == 0 for count in counts)

        summaries[source] = {
            "peak_day_files": peak_count,
            "peak_day_date": peak_date.isoformat(),
            "median_daily_files": median(counts),
            "no_file_days": no_file_days,
            "no_file_days_pct": no_file_days / len(counts) * 100,
        }

    return summaries


def run():
    queries = load_queries()
    spark = get_spark("e4")

    try:
        monthly_rows = spark.sql(queries["monthly_arrivals"]).collect()
        daily_rows = spark.sql(queries["daily_arrivals"]).collect()

        sources = sorted({row["source"] for row in monthly_rows})

        if not sources:
            raise RuntimeError("No arrival records found. Check that Task 14 data is available.")

        daily_summaries = build_daily_summaries(
            daily_rows,
            sources,
            config.DATA_START,
            config.DATA_END,
        )

        monthly_data = {
            (row["source"], int(row["arrival_year"]), int(row["arrival_month"])): (
                int(row["files"]),
                int(row["bytes"] or 0),
            )
            for row in monthly_rows
        }

        fieldnames = [
            "source",
            "year",
            "month",
            "files",
            "bytes",
            "mb",
            "peak_day_files",
            "peak_day_date",
            "median_daily_files",
            "no_file_days",
            "no_file_days_pct",
        ]

        with RESULTS_FILE.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()

            for source in sources:
                year = config.DATA_START.year
                month = config.DATA_START.month

                while (year, month) <= (
                    config.DATA_END.year,
                    config.DATA_END.month,
                ):
                    files, size_bytes = monthly_data.get((source, year, month), (0, 0))

                    writer.writerow(
                        {
                            "source": source,
                            "year": year,
                            "month": month,
                            "files": files,
                            "bytes": size_bytes,
                            "mb": round(size_bytes / 1_000_000, 3),
                            **daily_summaries[source],
                        }
                    )

                    if month == 12:
                        year += 1
                        month = 1
                    else:
                        month += 1

        print(f"E4 results saved to: {RESULTS_FILE}")
        print("\nArrival summary by source:")

        for source in sources:
            total_files = sum(
                files for (row_source, _, _), (files, _) in monthly_data.items() if row_source == source
            )
            total_bytes = sum(
                size for (row_source, _, _), (_, size) in monthly_data.items() if row_source == source
            )
            summary = daily_summaries[source]

            print(
                f"{source}: {total_files} files, "
                f"{total_bytes / 1_000_000:.2f} MB, "
                f"peak day {summary['peak_day_files']} files "
                f"({summary['peak_day_date']}), "
                f"median {summary['median_daily_files']} files/day, "
                f"{summary['no_file_days_pct']:.1f}% days with no files"
            )

    finally:
        spark.stop()


if __name__ == "__main__":
    run()
