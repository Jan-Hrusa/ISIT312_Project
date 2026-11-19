"""Compare Hive and Spark benchmark results."""

import csv
from pathlib import Path

path = Path("benchmarks/e5/results.csv")

if not path.exists():
    raise SystemExit("No results.csv yet. Run both benchmarks first.")

results = {}

with path.open(newline="", encoding="utf-8") as file:
    reader = csv.DictReader(file)
    for row in reader:
        key = (row["query"], row["engine"])
        results.setdefault(key, set()).add((int(row["rows"]), row["fingerprint"]))

failed = False

for query in ["q1", "q3", "q4", "q5", "v1"]:
    hive = results.get((query, "hive"))
    spark = results.get((query, "spark"))

    if not hive or not spark:
        print(f"{query}: INCOMPLETE — missing Hive or Spark results")
        failed = True
    elif len(hive) != 1 or len(spark) != 1:
        print(f"{query}: FAIL — inconsistent results across runs")
        failed = True
    elif hive == spark:
        print(f"{query}: PASS — row counts and fingerprints match")
    else:
        print(f"{query}: FAIL — Hive and Spark results differ")
        failed = True

raise SystemExit(1 if failed else 0)
