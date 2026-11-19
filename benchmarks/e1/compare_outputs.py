"""E1: the three versions' outputs, sorted and compared; any difference fails the experiment.

    python -m benchmarks.e1.compare_outputs   # <out>/e1/{mrjob,spark,hive}.tsv of the active dataset

Each output is (account, yyyy-MM, transactions, amount CZK), one row per account and month.
"""

from __future__ import annotations

import csv
import sys
from decimal import Decimal
from pathlib import Path

from common import config

VERSIONS = ("mrjob", "spark", "hive")
CENT = Decimal("0.01")


def output_dir() -> Path:
    return config.OUT_DIR / "e1"


def normalize(rows) -> list[tuple[str, str, int, Decimal]]:
    """The rows in one form for every version (account without leading zeros, amount to the haléř), sorted."""
    return sorted(
        (str(int(account)), str(month), int(count), Decimal(str(amount)).quantize(CENT))
        for account, month, count, amount in rows
    )


def write_output(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t").writerows(normalize(rows))


def read_output(path: Path) -> list[tuple[str, str, int, Decimal]]:
    with path.open(encoding="utf-8", newline="") as f:
        return normalize(csv.reader(f, delimiter="\t"))


def compare(outputs: dict[str, list]) -> list[str]:
    """Differences between the versions' outputs, each against the first; empty when all are identical."""
    (base_name, base), *others = [(name, normalize(rows)) for name, rows in outputs.items()]
    problems = []
    for name, rows in others:
        if rows == base:
            continue
        only_base, only_other = sorted(set(base) - set(rows)), sorted(set(rows) - set(base))
        problems.append(
            f"{name} differs from {base_name}: {len(rows)} vs {len(base)} rows, "
            f"{len(only_base)} only in {base_name} (first {only_base[:3]}), "
            f"{len(only_other)} only in {name} (first {only_other[:3]})"
        )
    return problems


def main() -> int:
    folder = output_dir()
    missing = [v for v in VERSIONS if not (folder / f"{v}.tsv").exists()]
    if missing:
        print(f"no output for {', '.join(missing)} in {folder}: run benchmarks.e1.run_e1 first")
        return 1
    outputs = {v: read_output(folder / f"{v}.tsv") for v in VERSIONS}
    problems = compare(outputs)
    for problem in problems:
        print(problem)
    if not problems:
        print(f"OK: {', '.join(VERSIONS)} identical ({len(outputs[VERSIONS[0]])} rows)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
