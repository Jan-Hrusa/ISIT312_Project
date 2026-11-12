
"""Tests for the Hive warehouse DDL and shared SQL runner."""

from pathlib import Path

import pytest

from warehouse.sql import named_queries, render, run_file


DDL = Path("warehouse/ddl/fve_dw.sql")

TABLES = {
    "dim_project",
    "dim_supplier",
    "dim_cost_category",
    "dim_date",
    "dim_bank_account",
    "fact_budget_line",
    "fact_invoice_line",
    "fact_payment",
    "fact_payment_order",
}

PARTITIONS = {
    "fact_budget_line": ["signed_year"],
    "fact_invoice_line": ["issue_year"],
    "fact_payment": ["pay_year", "pay_month"],
    "fact_payment_order": ["order_year"],
}


def test_render_replaces_variables(tmp_path):
    sql_file = tmp_path / "variables.sql"
    sql_file.write_text(
        "SELECT '${DW_DB}', '${LAKE_DW}', '${CUSTOM}';",
        encoding="utf-8",
    )

    statements = render(
        sql_file,
        DW_DB="test_dw",
        LAKE_DW="/test/dw",
        CUSTOM="hello",
    )

    assert statements == [
        "SELECT 'test_dw', '/test/dw', 'hello'"
    ]


def test_render_unknown_variable_fails(tmp_path):
    sql_file = tmp_path / "unknown.sql"
    sql_file.write_text(
        "SELECT '${DOES_NOT_EXIST}';",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="DOES_NOT_EXIST"):
        render(sql_file)


def test_named_queries(tmp_path):
    sql_file = tmp_path / "queries.sql"
    sql_file.write_text(
        """
-- name: first_query
SELECT '${DW_DB}';

-- name: second_query
SELECT 2;
""",
        encoding="utf-8",
    )

    queries = named_queries(sql_file, DW_DB="test_dw")

    assert queries == {
        "first_query": "SELECT 'test_dw'",
        "second_query": "SELECT 2",
    }


@pytest.fixture(scope="module")
def warehouse_spark(tmp_path_factory):
    """Create an isolated local Spark session with Hive support."""
    from pyspark.sql import SparkSession

    root = tmp_path_factory.mktemp("warehouse_spark")
    warehouse_dir = root / "warehouse"
    metastore_dir = root / "metastore"

    spark = (
        SparkSession.builder
        .master("local[2]")
        .appName("warehouse-ddl-tests")
        .config("spark.sql.warehouse.dir", warehouse_dir.as_uri())
        .config(
            "javax.jdo.option.ConnectionURL",
            f"jdbc:derby:;databaseName={metastore_dir};create=true",
        )
        .enableHiveSupport()
        .getOrCreate()
    )

    yield spark
    spark.stop()


@pytest.fixture(scope="module")
def created_warehouse(warehouse_spark, tmp_path_factory):
    """Run the DDL in a temporary database and local directory."""
    root = tmp_path_factory.mktemp("warehouse_tables")
    database = "fve_dw_test"

    statements = render(
        DDL,
        DW_DB=database,
        LAKE_DW=root.as_uri(),
    )

    for statement in statements:
        warehouse_spark.sql(statement)

    yield warehouse_spark, database

    warehouse_spark.sql(
        f"DROP DATABASE IF EXISTS {database} CASCADE"
    )


def test_ddl_runs_twice(created_warehouse):
    spark, database = created_warehouse

    statements = render(
        DDL,
        DW_DB=database,
        LAKE_DW=spark.sql(
            f"DESCRIBE DATABASE EXTENDED {database}"
        ).collect()[-1][1],
    )

    for statement in statements:
        spark.sql(statement)


def test_all_9_tables_exist(created_warehouse):
    spark, database = created_warehouse

    actual = {
        row.tableName
        for row in spark.sql(
            f"SHOW TABLES IN {database}"
        ).collect()
    }

    assert TABLES.issubset(actual)


def test_partition_columns(created_warehouse):
    spark, database = created_warehouse

    for table, expected in PARTITIONS.items():
        columns = spark.catalog.listColumns(table, database)
        actual = [
            column.name
            for column in columns
            if column.isPartition
        ]

        assert actual == expected, (
            f"{table}: expected {expected}, got {actual}"
        )


def test_tables_are_external_orc(created_warehouse):
    spark, database = created_warehouse

    for table in TABLES:
        rows = spark.sql(
            f"DESCRIBE FORMATTED {database}.{table}"
        ).collect()

        metadata = {
            str(row[0]).strip().rstrip(":"): str(row[1]).strip()
            for row in rows
            if row[0] is not None
        }

        assert metadata.get("Table Type") == "EXTERNAL_TABLE"
        assert "OrcInputFormat" in metadata.get("InputFormat", "")
