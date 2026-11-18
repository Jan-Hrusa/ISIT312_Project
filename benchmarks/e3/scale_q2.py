"""Experiment E3, scaling point: Q2 (photos and MB per project and month) at 1x to 10x the rows.

On the main dataset HBase also wins Q2 (README.md): Hive's GROUP BY is mostly fixed cost (planning and one
local MapReduce job), while HBase's scan grows with every row it sends through Thrift. This script finds where
that turns: for each factor it copies the catalogue rows that Q2 reads that many times into scratch stores,
times Q2 on both with run_e3's own functions and drops the copies again. Only metadata is copied (the photos'
`meta:size_bytes` in HBase, the `media_files` columns Q2 reads in Hive), so no x10 photo data is needed.
A copy is the same rows again with `-<k>` appended to the file_id, so every project and month keeps its
groups and the counts and bytes simply multiply; both stores must still agree. Factor 1 is copied too, so
every factor has the same layout (one ORC file, a fresh HBase table) and 1x is this machine's baseline.

Writes benchmarks/e3/results_scale.csv. Run in the client container with the core and hbase profiles up, after
the media and catalogue steps:

    python -m benchmarks.e3.scale_q2 [--factors 1 2 5 7 10] [--runs 10]
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from benchmarks.e3 import run_e3
from common import config
from common import spark as project_spark
from hbase import catalogue

RESULTS = Path(__file__).resolve().parent / "results_scale.csv"
COLUMNS = ("factor", "photos", "store", "run", "seconds", "groups")
SCRATCH_DB = "e3_scale_x{factor}"
SCRATCH_TABLE = "media_catalog_e3_x{factor}"
SIZE_COLUMN = b"meta:size_bytes"


def copy_stores(factor: int) -> tuple[str, str]:
    """Copy the Q2 inputs `factor` times into a scratch Hive database and HBase table; return their names."""
    db, table = SCRATCH_DB.format(factor=factor), SCRATCH_TABLE.format(factor=factor)
    spark = project_spark.get_spark(f"e3-scale-x{factor}")
    try:
        spark.sql(f"DROP DATABASE IF EXISTS {db} CASCADE")
        spark.sql(f"CREATE DATABASE {db} LOCATION '/tmp/{db}'")  # DROP ... CASCADE removes it
        # One ORC file, like the media job writes media_files, so Hive runs one map task at every factor.
        spark.sql(
            f"CREATE TABLE {db}.media_files STORED AS ORC AS"
            " SELECT /*+ REPARTITION(1) */ concat(file_id, '-', k) AS file_id, kind, project_code, taken_at,"
            f" size_bytes FROM {config.CLEAN_DB}.media_files"
            f" LATERAL VIEW explode(sequence(0, {factor - 1})) copies AS k"
        )
    finally:
        spark.stop()

    conn = catalogue.connect()
    try:
        if table.encode() in conn.tables():
            conn.delete_table(table, disable=True)
        conn.create_table(table, {"meta": {"max_versions": 1}})
        source = conn.table(config.HBASE_TABLE)
        with conn.table(table).batch(batch_size=5000) as batch:
            for key, data in source.scan(filter=run_e3.PHOTO_ROWS, columns=[SIZE_COLUMN]):
                for k in range(factor):
                    batch.put(key + f"-{k}".encode(), data)
    finally:
        conn.close()
    return db, table


def drop_stores(factor: int) -> None:
    db, table = SCRATCH_DB.format(factor=factor), SCRATCH_TABLE.format(factor=factor)
    conn = catalogue.connect()
    try:
        if table.encode() in conn.tables():
            conn.delete_table(table, disable=True)
    finally:
        conn.close()
    spark = project_spark.get_spark(f"e3-scale-drop-x{factor}")
    try:
        spark.sql(f"DROP DATABASE IF EXISTS {db} CASCADE")
    finally:
        spark.stop()


def time_q2(db: str, table: str, runs: int) -> dict:
    """run_e3's Q2 on the scratch stores: {store: (seconds per run, result)}; both stores must agree."""
    saved = config.CLEAN_DB, config.HBASE_TABLE
    config.CLEAN_DB, config.HBASE_TABLE = db, table
    hbase_conn = catalogue.connect()
    hive_conn, cursor = run_e3.hive_cursor()
    try:
        timings = {
            "HBase": run_e3.timed(lambda: run_e3.q2_hbase(hbase_conn), runs),
            "Hive": run_e3.timed(lambda: run_e3.q2_hive(cursor), runs),
        }
    finally:
        hbase_conn.close()
        hive_conn.close()
        config.CLEAN_DB, config.HBASE_TABLE = saved
    if timings["HBase"][1] != timings["Hive"][1]:
        raise RuntimeError(f"Q2 on {db}: HBase and Hive give different photo counts or sizes")
    return timings


def result_rows(factor: int, timings: dict[str, tuple[list[float], dict]]) -> list[dict]:
    """CSV rows: every run (run 1 = cold) and the median over runs 2..n, per store."""
    rows = []
    for store, (seconds, result) in timings.items():
        photos = sum(count for count, _ in result.values())
        runs = ["cold", *(str(i) for i in range(2, len(seconds) + 1))]
        rows += [
            {
                "factor": factor,
                "photos": photos,
                "store": store,
                "run": run,
                "seconds": s,
                "groups": len(result),
            }
            for run, s in zip(runs, seconds, strict=True)
        ]
        rows.append(
            {
                "factor": factor,
                "photos": photos,
                "store": store,
                "run": "median",
                "seconds": statistics.median(seconds[1:]),
                "groups": len(result),
            }
        )
    return rows


def summary(rows: list[dict]) -> list[tuple[int, int, float, float, str]]:
    """(factor, photos, HBase median, Hive median, faster store) per factor, smallest factor first."""
    medians = {(r["factor"], r["store"]): r for r in rows if r["run"] == "median"}
    out = []
    for factor in sorted({f for f, _ in medians}):
        hbase, hive = medians[(factor, "HBase")]["seconds"], medians[(factor, "Hive")]["seconds"]
        out.append(
            (factor, medians[(factor, "HBase")]["photos"], hbase, hive, "HBase" if hbase < hive else "Hive")
        )
    return out


def run(factors: list[int], runs: int, out: Path = RESULTS) -> list[dict]:
    if runs < 2:
        raise ValueError("runs must be at least 2: run 1 is the cold run, the median is over the rest")
    if any(f < 1 for f in factors):
        raise ValueError("factors must be 1 or more")
    rows = []
    for factor in factors:
        try:
            db, table = copy_stores(factor)
            rows += result_rows(factor, time_q2(db, table, runs))
        finally:
            drop_stores(factor)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**r, "seconds": f"{r['seconds']:.4f}"} for r in rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--factors", type=int, nargs="+", default=[1, 2, 5, 7, 10], help="copies of the rows")
    ap.add_argument("--runs", type=int, default=10, help="runs per factor and store (default 10)")
    args = ap.parse_args(argv)
    rows = run(args.factors, args.runs)
    print(f"{'factor':>6} {'photos':>8} {'HBase median s':>15} {'Hive median s':>14}  faster")
    for factor, photos, hbase, hive, faster in summary(rows):
        print(f"{factor:>6} {photos:>8} {hbase:>15.3f} {hive:>14.3f}  {faster}")
    print(f"written {RESULTS}")


if __name__ == "__main__":
    main()
