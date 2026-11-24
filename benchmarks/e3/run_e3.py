"""Experiment E3: two media questions against HBase (`media_catalog`) and Hive (`fve_clean.media_files`).

Q1 photos of one project in one month (a lookup): HBase range scan (`hbase.search.photos`), Hive
`SELECT ... WHERE project_code = ... AND taken_at in the month`.
Q2 photos and MB per project and month (an aggregation): HBase full scan of the PHOTO rows summed in Python,
Hive `GROUP BY project_code, month`.

Each question runs `--runs` times per store (default 10) on one open connection; run 1 is reported as cold,
the median is over the warm runs 2..n. Both stores must return the same rows for Q1 (the same file_ids) and Q2
(the same counts and bytes), otherwise the run stops. Writes benchmarks/e3/results.csv. Run in the client
container with the core and hbase profiles up, after the media and catalogue steps:

    python -m benchmarks.e3.run_e3 [--project FVE-2026-02 --month 2026-06] [--runs 10]
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from common import config
from hbase import catalogue, search

RESULTS = Path(__file__).resolve().parent / "results.csv"
COLUMNS = ("question", "store", "run", "seconds", "rows")
Q1 = "Q1 photos of one project in one month"
Q2 = "Q2 photos and MB per project and month"
# The PHOTO rows of every project: the kind is the second key field, so the region server filters them.
PHOTO_ROWS = b"RowFilter(=, 'regexstring:^[^#]+#PHOTO#')"
NO_TIME = "1970"  # photos without an EXIF time are keyed at 19700101000000; Hive has NULL for them


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-06' -> (1 Jun 2026, 30 Jun 2026)."""
    first = date.fromisoformat(f"{month}-01")
    after = (first + timedelta(days=32)).replace(day=1)
    return first, after - timedelta(days=1)


def q1_hbase(conn, project: str, month: str) -> list[str]:
    start, end = month_bounds(month)
    return sorted(p["file_id"] for p in search.photos(project, start, end, conn=conn))


def q1_hive(cursor, project: str, month: str) -> list[str]:
    start, end = month_bounds(month)
    cursor.execute(
        "SELECT file_id FROM media_files WHERE kind = 'PHOTO' AND project_code = %(project)s"
        " AND taken_at >= %(start)s AND taken_at < %(stop)s",
        {"project": project, "start": f"{start} 00:00:00", "stop": f"{end + timedelta(days=1)} 00:00:00"},
    )
    return sorted(r[0] for r in cursor.fetchall())


def q2_hbase(conn) -> dict[tuple[str, str], tuple[int, int]]:
    """(project, 'yyyy-MM') -> (photos, bytes) from a scan of every PHOTO row's size cell."""
    counts: Counter = Counter()
    sizes: Counter = Counter()
    table = conn.table(config.HBASE_TABLE)
    for key, data in table.scan(filter=PHOTO_ROWS, columns=[b"meta:size_bytes"]):
        project, _, key_time, _ = key.decode().split(catalogue.SEP)
        if key_time.startswith(NO_TIME):
            continue
        group = (project, f"{key_time[:4]}-{key_time[4:6]}")
        counts[group] += 1
        sizes[group] += int(data[b"meta:size_bytes"])
    return {g: (counts[g], sizes[g]) for g in counts}


def q2_hive(cursor) -> dict[tuple[str, str], tuple[int, int]]:
    cursor.execute(
        "SELECT project_code, date_format(taken_at, 'yyyy-MM') AS month, count(*), sum(size_bytes)"
        " FROM media_files WHERE kind = 'PHOTO' AND taken_at IS NOT NULL"
        " GROUP BY project_code, date_format(taken_at, 'yyyy-MM')"
    )
    return {(p, m): (int(n), int(b)) for p, m, n, b in cursor.fetchall()}


def timed(fn, runs: int) -> tuple[list[float], object]:
    seconds, result = [], None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = fn()
        seconds.append(time.perf_counter() - t0)
    return seconds, result


def result_rows(question: str, store: str, seconds: list[float], rows: int) -> list[dict]:
    out = [
        {
            "question": question,
            "store": store,
            "run": "cold" if i == 0 else str(i + 1),
            "seconds": s,
            "rows": rows,
        }
        for i, s in enumerate(seconds)
    ]
    out.append(
        {
            "question": question,
            "store": store,
            "run": "median",
            "seconds": statistics.median(seconds[1:]),
            "rows": rows,
        }
    )
    return out


def hive_cursor():
    from pyhive import hive

    conn = hive.Connection(
        host=config.HIVE_HOST, port=config.HIVE_PORT, username="hive", database=config.CLEAN_DB
    )
    return conn, conn.cursor()


def run(project: str, month: str, runs: int, out: Path = RESULTS) -> list[dict]:
    if runs < 2:
        raise ValueError("runs must be at least 2: run 1 is the cold run, the median is over the rest")
    hbase_conn = catalogue.connect()
    hive_conn, cursor = hive_cursor()
    try:
        q1 = {
            "HBase": timed(lambda: q1_hbase(hbase_conn, project, month), runs),
            "Hive": timed(lambda: q1_hive(cursor, project, month), runs),
        }
        q2 = {
            "HBase": timed(lambda: q2_hbase(hbase_conn), runs),
            "Hive": timed(lambda: q2_hive(cursor), runs),
        }
    finally:
        hbase_conn.close()
        hive_conn.close()

    if q1["HBase"][1] != q1["Hive"][1]:
        raise RuntimeError(f"Q1: HBase and Hive return different photos for {project} {month}")
    if not q1["HBase"][1]:
        raise RuntimeError(f"Q1: {project} has no photos in {month}; pick a month with photos")
    if q2["HBase"][1] != q2["Hive"][1]:
        raise RuntimeError("Q2: HBase and Hive give different photo counts or sizes per project and month")

    rows = []
    for question, results in ((Q1, q1), (Q2, q2)):
        for store, (seconds, result) in results.items():
            rows += result_rows(question, store, seconds, len(result))
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows({**r, "seconds": f"{r['seconds']:.4f}"} for r in rows)
    return rows


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default="FVE-2026-02", help="Q1 project (default FVE-2026-02)")
    ap.add_argument("--month", default="2026-06", help="Q1 month yyyy-MM (default 2026-06)")
    ap.add_argument("--runs", type=int, default=10, help="runs per question and store (default 10)")
    args = ap.parse_args(argv)
    rows = run(args.project, args.month, args.runs)
    print(f"{'question':<40} {'store':<6} {'cold s':>8} {'median s':>9} {'rows':>6}")
    for r in rows:
        if r["run"] == "cold":
            median = next(
                m
                for m in rows
                if m["run"] == "median" and m["question"] == r["question"] and m["store"] == r["store"]
            )
            print(
                f"{r['question']:<40} {r['store']:<6} {r['seconds']:>8.3f} "
                f"{median['seconds']:>9.3f} {r['rows']:>6}"
            )
    print(f"written {RESULTS}")


if __name__ == "__main__":
    main()
