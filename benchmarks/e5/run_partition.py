"""Run the E5 partition-pruning experiment."""

import argparse
import csv
from pathlib import Path

from benchmarks.e5.run_e5 import execute_query
from warehouse.sql import render

SQL_FILE = Path("benchmarks/e5/partition_test.sql")


def main():
    parser = argparse.ArgumentParser(description="E5 partition benchmark")
    parser.add_argument("--database", default="fve_dw_x10")
    parser.add_argument("--engine", choices=["hive", "spark"], default="hive")
    args = parser.parse_args()

    statements = render(SQL_FILE, DW_DB=args.database)

    if len(statements) != 6:
        raise ValueError("Expected six partition experiment statements")

    connections = {
        "hive": ("hiveserver2", 10000, "hive"),
        "spark": ("sparksql", 10001, "hadoop"),
    }
    host, port, username = connections[args.engine]

    labels = [
        "drop_flat",
        "create_flat",
        "partitioned",
        "unpartitioned",
        "explain_partitioned",
        "explain_unpartitioned",
    ]

    output = Path("benchmarks/e5/partition_results.csv")

    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["statement", "engine", "seconds", "rows", "result"])

        for label, sql in zip(labels, statements, strict=True):
            seconds, rows = execute_query(host, port, username, sql)
            result = repr(rows) if label in ("partitioned", "unpartitioned") else ""
            writer.writerow([label, args.engine, round(seconds, 3), len(rows), result])
            file.flush()
            print(f"{label}: {seconds:.3f}s, {len(rows)} rows", flush=True)

            if label.startswith("explain_"):
                plan = Path(f"benchmarks/e5/{label}_{args.engine}.txt")
                plan.write_text(
                    "\n".join(str(row[0]) for row in rows),
                    encoding="utf-8",
                )


if __name__ == "__main__":
    main()
