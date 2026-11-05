"""Create, write and read the clean-zone tables defined in common/schemas.py."""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from common import config
from common.schemas import CLEAN_PARTITIONS, CLEAN_TABLES

# Tables with their own writer: ingest_log is append only (common.lake.append_ingest_log, Task 14.1);
# dq_issues replaces one job's partition (common.dq.write_issues).
_OWN_WRITER = {
    "ingest_log": "ingest_log is append only: use common.lake.append_ingest_log",
    "dq_issues": "dq_issues is written per job: use common.dq.write_issues",
}


def table_location(table: str) -> str:
    """HDFS folder of a clean table: `<LAKE_CLEAN>/<table>`."""
    return f"{config.LAKE_CLEAN}/{table}"


def qualified_name(table: str) -> str:
    """`<CLEAN_DB>.<table>`."""
    return f"{config.CLEAN_DB}.{table}"


def create_table_sql(table: str) -> str:
    """`CREATE EXTERNAL TABLE IF NOT EXISTS ...` for one clean table, generated from the contract."""
    _check_table(table)
    columns = ",\n  ".join(f"`{name}` {hive_type}" for name, hive_type in CLEAN_TABLES[table])
    partitions = CLEAN_PARTITIONS.get(table)
    partitioned_by = ""
    if partitions:
        partitioned_by = "\nPARTITIONED BY (" + ", ".join(f"`{n}` {t}" for n, t in partitions) + ")"
    return (
        f"CREATE EXTERNAL TABLE IF NOT EXISTS {qualified_name(table)} (\n  {columns}\n)"
        f"{partitioned_by}\nSTORED AS ORC\nLOCATION '{table_location(table)}'"
    )


def create_clean_tables(spark: SparkSession) -> list[str]:
    """Create `CLEAN_DB` and every clean table that doesn't exist yet; return the table names."""
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {config.CLEAN_DB}")
    for table in CLEAN_TABLES:
        spark.sql(create_table_sql(table))
    return list(CLEAN_TABLES)


def contract_select(df: DataFrame, table: str) -> DataFrame:
    """The contract columns of `table` from `df`, in contract order and cast to contract types.

    Raises ValueError("missing columns for <table>: a, b") if any contract column is missing; extra columns
    are dropped.
    """
    _check_table(table)
    missing = [name for name, _ in CLEAN_TABLES[table] if name not in df.columns]
    if missing:
        raise ValueError(f"missing columns for {table}: {', '.join(missing)}")
    return df.select([F.col(name).cast(hive_type).alias(name) for name, hive_type in CLEAN_TABLES[table]])


def write_table(spark: SparkSession, df: DataFrame, table: str) -> None:
    """Replace the whole content of a clean table with `df` (jobs recompute their tables on every run)."""
    if table in _OWN_WRITER:
        raise ValueError(_OWN_WRITER[table])
    contract_select(df, table).write.insertInto(qualified_name(table), overwrite=True)


def read_table(spark: SparkSession, table: str) -> DataFrame:
    """A clean table as a DataFrame."""
    _check_table(table)
    return spark.table(qualified_name(table))


def _check_table(table: str) -> None:
    if table not in CLEAN_TABLES:
        raise ValueError(f"unknown table: {table}")
