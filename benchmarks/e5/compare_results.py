"""Experiment E5: check benchmarks/e5/results.csv and print the cold/warm table of the README.

Checks: every query of run_e5 has the same rows on Hive and on Spark (one row count and fingerprint across all
runs of both engines), and the partition test's two queries (`partition_yes`, `partition_no`) return the
same result on the partitioned table and on its flat copy. Then prints, per query, the cold run (run 1) and
the median of the warm runs (2..n) on both engines with Spark's warm speedup. Exit code 1 if a check fails.

    python -m benchmarks.e5.compare_results
"""

from __future__ import annotations

from pathlib import Path

from benchmarks.e5.run_e5 import QUERY_FILES, RESULTS, cold_and_warm, read_results

PARTITION_QUERIES = ("partition_yes", "partition_no")


def checks(rows: list[dict]) -> list[tuple[str, bool, str]]:
    """(name, passed, message) per query of run_e5 and one for the partition test."""
    results: dict[tuple[str, str], set] = {}
    for r in rows:
        results.setdefault((r["query"], r["engine"]), set()).add((int(r["rows"]), r["fingerprint"]))

    out = []
    for query in QUERY_FILES:
        hive, spark = results.get((query, "hive")), results.get((query, "spark"))
        if not hive or not spark:
            out.append((query, False, "INCOMPLETE: missing Hive or Spark results"))
        elif len(hive) != 1 or len(spark) != 1:
            out.append((query, False, "FAIL: results differ between runs"))
        elif hive != spark:
            out.append((query, False, "FAIL: Hive and Spark results differ"))
        else:
            out.append((query, True, "PASS: row counts and fingerprints match"))

    partition = [results[k] for k in results if k[0] in PARTITION_QUERIES]
    if not partition:
        out.append(("partition", False, "INCOMPLETE: no partition test rows"))
    elif len(set.union(*partition)) != 1:
        out.append(("partition", False, "FAIL: partitioned and flat tables (or the engines) differ"))
    else:
        out.append(("partition", True, "PASS: same result on the partitioned table and the flat copy"))
    return out


def table(rows: list[dict]) -> list[tuple[str, float, float, float, float, float]]:
    """(query, Hive cold, Spark cold, Hive warm, Spark warm, warm speedup) per query with warm runs."""
    out = []
    for query in (*QUERY_FILES, *PARTITION_QUERIES):
        runs = {
            e: {r["run"] for r in rows if r["query"] == query and r["engine"] == e} for e in ("hive", "spark")
        }
        if all("1" in r and len(r) >= 2 for r in runs.values()):
            hive_cold, hive_warm = cold_and_warm(rows, query, "hive")
            spark_cold, spark_warm = cold_and_warm(rows, query, "spark")
            out.append((query, hive_cold, spark_cold, hive_warm, spark_warm, hive_warm / spark_warm))
    return out


def main(path: Path = RESULTS) -> int:
    rows = read_results(path)
    if not rows:
        print(f"No rows in {path}: run benchmarks.e5.run_e5 for both engines first.")
        return 1
    results = checks(rows)
    for name, _, message in results:
        print(f"{name}: {message}")
    print()
    header = ("query", "Hive cold", "Spark cold", "Hive warm", "Spark warm", "speedup")
    print(f"{header[0]:<14} " + " ".join(f"{h:>11}" for h in header[1:]))
    for query, hive_cold, spark_cold, hive_warm, spark_warm, speedup in table(rows):
        print(
            f"{query:<14} {hive_cold:>11.1f} {spark_cold:>11.2f} {hive_warm:>11.1f} {spark_warm:>11.2f} "
            f"{speedup:>10.1f}x"
        )
    return 0 if all(passed for _, passed, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
