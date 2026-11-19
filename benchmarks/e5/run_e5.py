"""Experiment E5: Hive MapReduce versus Spark SQL benchmarks."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from time import perf_counter

from pyhive import hive

from warehouse.sql import named_queries

QUERY_DIR = Path("warehouse/queries")

QUERY_FILES = {
    "q1": "q1_budget_vs_actual.sql",
    "q3": "q3_cumulative_spend.sql",
    "q4": "q4_overrun_rank.sql",
    "q5": "q5_cost_per_mwp.sql",
    "v1": "v1_project_list.sql",
}


def load_queries(database: str) -> dict[str, str]:
    """Load the five dashboard queries for the selected database."""
    queries = {}

    for query_id, filename in QUERY_FILES.items():
        path = QUERY_DIR / filename
        named = named_queries(path, DW_DB=database)

        if len(named) != 1:
            raise ValueError(f"Expected one named query in {path}")

        queries[query_id] = next(iter(named.values()))

    return queries


def execute_query(
    host: str,
    port: int,
    username: str,
    sql: str,
) -> tuple[float, list[tuple]]:
    """Time SQL execution through fetching the final result row."""
    connection = hive.Connection(
        host=host,
        port=port,
        username=username,
    )
    try:
        cursor = connection.cursor()
        try:
            if port == 10000:
                cursor.execute("SET hive.execution.engine=mr")
                cursor.execute("SET mapreduce.framework.name=yarn")
                cursor.execute("SET hive.exec.mode.local.auto=false")

            start = perf_counter()
            cursor.execute(sql)
            rows = [] if sql.lstrip().upper().startswith(("DROP ", "CREATE ")) else cursor.fetchall()
            seconds = perf_counter() - start
            return seconds, rows
        finally:
            cursor.close()
    finally:
        connection.close()


def result_fingerprint(rows: list[tuple]) -> str:
    """Hash sorted query results for cross-engine comparison."""
    normalized = [
        json.dumps(
            [str(value) if value is not None else None for value in row],
            ensure_ascii=False,
        )
        for row in rows
    ]
    normalized.sort()
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Experiment E5 benchmark")
    parser.add_argument("--engine", choices=["hive", "spark"], required=True)
    parser.add_argument("--database", default="fve_dw_x10")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    if args.runs < 1:
        parser.error("--runs must be at least 1")

    settings = {
        "hive": ("hiveserver2", 10000, "hive"),
        "spark": ("sparksql", 10001, "hadoop"),
    }

    host, port, username = settings[args.engine]
    queries = load_queries(args.database)

    output = Path("benchmarks/e5/results.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output.exists() or output.stat().st_size == 0

    with output.open("a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if write_header:
            writer.writerow(["query", "engine", "run", "seconds", "rows", "fingerprint"])

        for query_id, sql in queries.items():
            for run in range(1, args.runs + 1):
                seconds, rows = execute_query(host, port, username, sql)

                fingerprint = result_fingerprint(rows)
                writer.writerow(
                    [
                        query_id,
                        args.engine,
                        run,
                        round(seconds, 3),
                        len(rows),
                        fingerprint,
                    ]
                )
                file.flush()
                print(f"  SHA256: {fingerprint}", flush=True)

                print(
                    f"{query_id} | {args.engine} | run {run} | {seconds:.3f}s | {len(rows)} rows",
                    flush=True,
                )


if __name__ == "__main__":
    main()
