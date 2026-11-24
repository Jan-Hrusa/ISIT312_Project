"""E1 version B: transactions and amount per account and month from GPC statements, with Spark on YARN.

Reuses Task 16's parser (`processing.bank.gpc.parse`); the YARN containers don't have the repo, so
`processing/` and `common/` are zipped and shipped with `addPyFile` first.
"""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from common.spark import get_spark

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("processing", "common")


def ship_repo(spark: SparkSession) -> None:
    """Zip `processing/` and `common/` and add them to every executor's Python path."""
    target = Path(tempfile.mkdtemp(prefix="e1_")) / "repo.zip"
    with zipfile.ZipFile(target, "w") as zf:
        for package in PACKAGES:
            for path in sorted((ROOT / package).rglob("*.py")):
                zf.write(path, path.relative_to(ROOT).as_posix())
    spark.sparkContext.addPyFile(str(target))


def monthly(spark: SparkSession, input_path: str) -> list[tuple]:
    """(account, yyyy-MM, transactions, amount CZK) for every GPC file under `input_path`."""

    # Defined here so Spark ships the function itself: executors get `processing`, not `benchmarks`.
    def transactions(item):
        from processing.bank.gpc import parse

        path, data = item
        _, rows = parse(data.decode("ascii"), path)
        return [(t["account"], t["value_date"], t["amount"]) for t in rows]

    rows = spark.sparkContext.binaryFiles(f"{input_path.rstrip('/')}/*.gpc").flatMap(transactions)
    df = spark.createDataFrame(rows, "account STRING, value_date DATE, amount DECIMAL(14,2)")
    result = (
        df.groupBy("account", F.date_format("value_date", "yyyy-MM").alias("month"))
        .agg(F.count("*").alias("transactions"), F.sum("amount").alias("amount"))
        .collect()
    )
    return [(r.account, r.month, r.transactions, r.amount) for r in result]


def run(input_path: str) -> list[tuple]:
    """One timed E1 run: a fresh YARN application, the aggregation, then stop."""
    spark = get_spark("e1", master="yarn", hive=False)
    try:
        ship_repo(spark)
        return monthly(spark, input_path)
    finally:
        spark.stop()
