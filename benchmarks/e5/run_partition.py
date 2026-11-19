"""Experiment E5, partition pruning: a year filter on fact_invoice_line and on an unpartitioned copy.

benchmarks/e5/partition_test.sql: CTAS `fact_invoice_line_flat` (unpartitioned copy), the 2025 query on both
tables, EXPLAIN EXTENDED of both (which partitions/files each plan reads, Lab 5 B2), then the copy is dropped
again so the warehouse holds only the contract's tables.

Writes, per engine: the two queries' timed runs into results.csv (`partition_yes` = partitioned table,
`partition_no` = flat copy; run 1 cold, runs 2..n warm; same columns and replace rule as run_e5), every
statement's time (run 1 for the timed ones) and result into partition_results_<engine>.csv, and the plans into
explain_<partitioned|unpartitioned>_<engine>.txt.

    python -m benchmarks.e5.run_partition --engine hive     # profiles core + yarn
    python -m benchmarks.e5.run_partition --engine spark    # profiles core + zeppelin (service sparksql)
"""

from __future__ import annotations

import argparse
import csv

from benchmarks.e5.run_e5 import ENGINES, HERE, execute_query, timed_row, write_results
from warehouse.sql import render

SQL_FILE = HERE / "partition_test.sql"
LABELS = (
    "drop_flat",
    "create_flat",
    "partitioned",
    "unpartitioned",
    "explain_partitioned",
    "explain_unpartitioned",
    "drop_flat_end",
)
TIMED = {"partitioned": "partition_yes", "unpartitioned": "partition_no"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--database", default="fve_dw_x10")
    parser.add_argument("--engine", choices=ENGINES, required=True)
    parser.add_argument("--runs", type=int, default=3, help="runs of each timed query (default 3)")
    args = parser.parse_args(argv)
    if args.runs < 2:
        parser.error("--runs must be at least 2: run 1 is the cold run, the warm median needs run 2")

    statements = render(SQL_FILE, DW_DB=args.database)
    if len(statements) != len(LABELS):
        raise ValueError(f"Expected {len(LABELS)} statements in {SQL_FILE}, got {len(statements)}")

    timed_rows = []
    with (HERE / f"partition_results_{args.engine}.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["statement", "engine", "seconds", "rows", "result"])
        for label, sql in zip(LABELS, statements, strict=True):
            if label in TIMED:
                runs = [timed_row(args.engine, TIMED[label], run, sql) for run in range(1, args.runs + 1)]
                timed_rows += [row for row, _ in runs]
                seconds, rows = float(runs[0][0]["seconds"]), runs[0][1]
            else:
                seconds, rows = execute_query(args.engine, sql)
            result = repr(rows) if label in TIMED else ""
            writer.writerow([label, args.engine, round(seconds, 3), len(rows), result])
            file.flush()
            print(f"{label}: {seconds:.3f}s, {len(rows)} rows", flush=True)
            if label.startswith("explain_"):
                plan = HERE / f"{label}_{args.engine}.txt"
                plan.write_text("\n".join(str(row[0]) for row in rows), encoding="utf-8")
    write_results(timed_rows)


if __name__ == "__main__":
    main()
