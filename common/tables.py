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
    """Replace the whole content of a clean table with `df` (jobs recompute their tables on every run).

    Raises ValueError
    - when a value can't be cast to its contract type (e.g. a date in another format or a number with a
      decimal comma), instead of writing NULL; columns that already have the contract type are not checked;
    - when the existing table's columns differ from the contract (a table created before a contract change):
      drop it and run create_clean_tables again (the tables are EXTERNAL, so the files stay).
    Never overwrite a table that `df` itself reads: Spark refuses to overwrite a path it is reading, so
    compute the new content from other tables.
    """
    if table in _OWN_WRITER:
        raise ValueError(_OWN_WRITER[table])
    out = contract_select(df, table)
    _check_casts(df, table)
    _check_existing_schema(spark, table)
    out.write.insertInto(qualified_name(table), overwrite=True)


def read_table(spark: SparkSession, table: str) -> DataFrame:
    """A clean table as a DataFrame."""
    _check_table(table)
    return spark.table(qualified_name(table))


def _check_casts(df: DataFrame, table: str) -> None:
    sums = []
    for name, hive_type in CLEAN_TABLES[table]:
        if df.schema[name].dataType.simpleString().lower() in (hive_type.lower(), "void"):
            continue
        bad = F.col(name).isNotNull() & F.col(name).cast(hive_type).isNull()
        sums.append(F.sum(F.when(bad, 1).otherwise(0)).alias(name))
    if not sums:
        return
    counts = {name: n for name, n in df.agg(*sums).first().asDict().items() if n}
    if counts:
        detail = ", ".join(f"{name} ({n} rows)" for name, n in counts.items())
        raise ValueError(f"values that can't be cast to the contract type in {table}: {detail}")


def _check_existing_schema(spark: SparkSession, table: str) -> None:
    expected = [(n.lower(), t.lower()) for n, t in CLEAN_TABLES[table] + CLEAN_PARTITIONS.get(table, [])]
    actual = [
        (f.name.lower(), f.dataType.simpleString().lower()) for f in spark.table(qualified_name(table)).schema
    ]
    if actual != expected:
        raise ValueError(
            f"{qualified_name(table)} differs from the contract (created before a contract change?): "
            "drop it and run common.tables.create_clean_tables (EXTERNAL table: the files stay)"
        )


def _check_table(table: str) -> None:
    if table not in CLEAN_TABLES:
        raise ValueError(f"unknown table: {table}")
