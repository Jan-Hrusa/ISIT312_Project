"""Data-quality issues: the rows of `fve_clean.dq_issues` that feed the "to fix" list."""

from __future__ import annotations

from collections.abc import Iterable

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

from common.tables import qualified_name, table_location

ISSUE_TYPES = (
    "DUPLICATE",
    "MISSING_VS",
    "NO_PROJECT",
    "PARSE_ERROR",
    "UNMATCHED_PAYMENT",
    "ORDER_NOT_CLEARED",
    "NO_GPS",
    "UNASSIGNED_PHOTO",
    "OVERRUN",
    "WRONG_VERSION",
)
JOBS = ("ingest", "bank", "finance", "matching", "media")

# What a job passes to write_issues; issue_id, detected_at and job are added there.
ISSUE_COLUMNS = ("issue_type", "source", "record_ref", "project_code", "detail")
ISSUE_SCHEMA = StructType([StructField(name, StringType(), True) for name in ISSUE_COLUMNS])


def issue_rows(spark: SparkSession, rows: Iterable[tuple | dict]) -> DataFrame:
    """A DataFrame of issues from Python rows (tuples in ISSUE_COLUMNS order, or dicts); may be empty."""
    tuples = [tuple(r.get(c) for c in ISSUE_COLUMNS) if isinstance(r, dict) else tuple(r) for r in rows]
    return spark.createDataFrame(tuples, ISSUE_SCHEMA)


def write_issues(spark: SparkSession, df: DataFrame, job: str) -> int:
    """Replace partition `job=<job>` of dq_issues with the issues in `df`; return how many were written.

    df has the columns ISSUE_COLUMNS. The partition is dropped and its folder deleted first (the table is
    EXTERNAL), so an empty df clears the job's issues and a re-run never duplicates them.
    Raises ValueError("unknown job: <x>") or ValueError("unknown issue_type: <x>") before anything changes.
    """
    if job not in JOBS:
        raise ValueError(f"unknown job: {job}")
    missing = [c for c in ISSUE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns for dq_issues: {', '.join(missing)}")
    issues = df.select([F.col(c).cast("string").alias(c) for c in ISSUE_COLUMNS]).cache()
    try:
        types = {row.issue_type for row in issues.select("issue_type").distinct().collect()}
        unknown = sorted(str(t) for t in types if t not in ISSUE_TYPES)
        if unknown:
            raise ValueError(f"unknown issue_type: {unknown[0]}")

        _drop_partition(spark, job)
        out = issues.select(
            F.expr("uuid()").alias("issue_id"),
            *ISSUE_COLUMNS,
            F.current_timestamp().alias("detected_at"),
            F.lit(job).alias("job"),
        )
        out.write.insertInto(qualified_name("dq_issues"), overwrite=False)
        return issues.count()
    finally:
        issues.unpersist()


def _drop_partition(spark: SparkSession, job: str) -> None:
    spark.sql(f"ALTER TABLE {qualified_name('dq_issues')} DROP IF EXISTS PARTITION (job='{job}')")
    jvm = spark.sparkContext._jvm
    path = jvm.org.apache.hadoop.fs.Path(f"{table_location('dq_issues')}/job={job}")
    fs = path.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    if fs.exists(path):
        fs.delete(path, True)
