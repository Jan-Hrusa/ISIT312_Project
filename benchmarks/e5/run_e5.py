"""Experiment E5: the dashboard queries on Hive (MapReduce on YARN) and on Spark SQL (Spark Thrift Server).

The five queries q1, q3, q4, q5 and v1 (warehouse/queries) run `--runs` times per engine through HiveServer2's
protocol (pyhive); each run opens its own connection and is timed until the last row is fetched. Run 1 is the
cold run, runs 2..n are warm. Every run's rows get a SHA-256 fingerprint of the sorted rows, so
`benchmarks.e5.compare_results` can show that both engines return the same result.

Rows go to benchmarks/e5/results.csv (query, engine, run, seconds, rows, fingerprint). A run replaces that
engine's earlier rows for the same queries and keeps every other row, so the two engines can run one after the
other (on an 8 GB laptop they don't fit together) and a rerun adds no duplicates. Run in the client container:

    python -m benchmarks.e5.run_e5 --engine hive     # profiles core + yarn
    python -m benchmarks.e5.run_e5 --engine spark    # profiles core + zeppelin (service sparksql)

`--database` defaults to fve_dw_x10 (load it first, README.md).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path
from time import perf_counter

from common import config
from warehouse.sql import named_queries

HERE = Path(__file__).resolve().parent
QUERY_DIR = HERE.parents[1] / "warehouse" / "queries"
RESULTS = HERE / "results.csv"
COLUMNS = ("query", "engine", "run", "seconds", "rows", "fingerprint")

QUERY_FILES = {
    "q1": "q1_budget_vs_actual.sql",
    "q3": "q3_cumulative_spend.sql",
    "q4": "q4_overrun_rank.sql",
    "q5": "q5_cost_per_mwp.sql",
    "v1": "v1_project_list.sql",
}
ENGINES = ("hive", "spark")
# host, port, user per engine; the Spark Thrift Server is the `sparksql` service of the zeppelin profile.
CONNECTIONS = {
    "hive": (config.HIVE_HOST, config.HIVE_PORT, "hive"),
    "spark": ("sparksql", config.SPARKSQL_PORT, "hadoop"),
}
# HiveServer2 runs MapReduce in local mode by default (docker/conf/hive-site.xml); E5 measures it on YARN.
HIVE_ON_YARN = (
    "SET hive.execution.engine=mr",
    "SET mapreduce.framework.name=yarn",
    "SET hive.exec.mode.local.auto=false",
)
NO_RESULT = ("DROP ", "CREATE ")


def load_queries(database: str) -> dict[str, str]:
    """The five dashboard queries rendered for `database`, by query id."""
    queries = {}
    for query_id, filename in QUERY_FILES.items():
        path = QUERY_DIR / filename
        named = named_queries(path, DW_DB=database)
        if len(named) != 1:
            raise ValueError(f"Expected one named query in {path}")
        queries[query_id] = next(iter(named.values()))
    return queries


def execute_query(engine: str, sql: str) -> tuple[float, list[tuple]]:
    """Run `sql` on `engine` on a new connection: (seconds until the last row is fetched, rows).

    The Hive session settings are sent before the clock starts. DROP and CREATE return no rows.
    """
    from pyhive import hive

    host, port, username = CONNECTIONS[engine]
    connection = hive.Connection(host=host, port=port, username=username)
    try:
        cursor = connection.cursor()
        try:
            if engine == "hive":
                for setting in HIVE_ON_YARN:
                    cursor.execute(setting)
            start = perf_counter()
            cursor.execute(sql)
            rows = [] if sql.lstrip().upper().startswith(NO_RESULT) else cursor.fetchall()
            return perf_counter() - start, rows
        finally:
            cursor.close()
    finally:
        connection.close()


def result_fingerprint(rows: list[tuple]) -> str:
    """SHA-256 of the rows as text, sorted, so the row order of an engine doesn't matter."""
    normalized = sorted(
        json.dumps([None if value is None else str(value) for value in row], ensure_ascii=False)
        for row in rows
    )
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def read_results(path: Path = RESULTS) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_results(new_rows: list[dict], path: Path = RESULTS) -> list[dict]:
    """Replace the rows of the same (query, engine) pairs in `path` with `new_rows`; keep every other row."""
    replaced = {(r["query"], r["engine"]) for r in new_rows}
    rows = [r for r in read_results(path) if (r["query"], r["engine"]) not in replaced] + new_rows
    order = list(QUERY_FILES)
    rows.sort(
        key=lambda r: (
            ENGINES.index(r["engine"]),
            order.index(r["query"]) if r["query"] in order else len(order),
            r["query"],
            int(r["run"]),
        )
    )
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({c: r[c] for c in COLUMNS} for r in rows)
    return rows


def timed_row(engine: str, query_id: str, run: int, sql: str) -> tuple[dict, list[tuple]]:
    """One timed execution: (its results.csv row, the rows it returned)."""
    seconds, rows = execute_query(engine, sql)
    fingerprint = result_fingerprint(rows)
    print(f"{query_id} | {engine} | run {run} | {seconds:.3f}s | {len(rows)} rows", flush=True)
    row = {
        "query": query_id,
        "engine": engine,
        "run": str(run),
        "seconds": f"{seconds:.3f}",
        "rows": str(len(rows)),
        "fingerprint": fingerprint,
    }
    return row, rows


def time_runs(engine: str, query_id: str, sql: str, runs: int) -> list[dict]:
    """`runs` timed executions of one statement as results.csv rows (run 1 = cold)."""
    return [timed_row(engine, query_id, run, sql)[0] for run in range(1, runs + 1)]


def cold_and_warm(rows: list[dict], query: str, engine: str) -> tuple[float, float]:
    """(cold = run 1, warm = median of runs 2..n) seconds of one query on one engine."""
    seconds = {
        int(r["run"]): float(r["seconds"]) for r in rows if r["query"] == query and r["engine"] == engine
    }
    if 1 not in seconds or len(seconds) < 2:
        raise ValueError(f"{query} on {engine}: needs run 1 and at least one warm run")
    return seconds[1], statistics.median(s for run, s in seconds.items() if run > 1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--engine", choices=ENGINES, required=True)
    parser.add_argument("--database", default="fve_dw_x10")
    parser.add_argument("--runs", type=int, default=3, help="runs per query (default 3: 1 cold + 2 warm)")
    args = parser.parse_args(argv)
    if args.runs < 2:
        parser.error("--runs must be at least 2: run 1 is the cold run, the warm median needs run 2")

    new_rows = []
    for query_id, sql in load_queries(args.database).items():
        new_rows += time_runs(args.engine, query_id, sql, args.runs)
    write_results(new_rows)
    print(f"written {RESULTS}")


if __name__ == "__main__":
    main()
