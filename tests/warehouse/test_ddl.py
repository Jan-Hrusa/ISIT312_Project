"""Tests for the Hive warehouse DDL and shared SQL runner."""

import uuid
from pathlib import Path

import pytest

from warehouse.sql import named_queries, render, run_file

DDL = Path(__file__).resolve().parents[2] / "warehouse" / "ddl" / "fve_dw.sql"

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
    sql_file.write_text("SELECT '${DW_DB}', '${LAKE_DW}', '${CUSTOM}';", encoding="utf-8")

    statements = render(sql_file, DW_DB="test_dw", LAKE_DW="/test/dw", CUSTOM="hello")

    assert statements == ["SELECT 'test_dw', '/test/dw', 'hello'"]


def test_render_unknown_variable_fails(tmp_path):
    sql_file = tmp_path / "unknown.sql"
    sql_file.write_text("SELECT '${DOES_NOT_EXIST}';", encoding="utf-8")

    with pytest.raises(ValueError, match="DOES_NOT_EXIST"):
        render(sql_file)


def test_render_ignores_variables_in_comments(tmp_path):
    sql_file = tmp_path / "comment.sql"
    sql_file.write_text("-- run with ${SOMETHING_ELSE}\nSELECT '${DW_DB}';", encoding="utf-8")

    assert render(sql_file, DW_DB="test_dw") == ["SELECT 'test_dw'"]


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


@pytest.fixture
def created_warehouse(spark_hive, tmp_path):
    """The DDL run once through run_file in a fresh database and a temporary lake folder.

    Uses conftest's `spark_hive` (local Derby metastore), so the tests never reach the stack's metastore, also
    inside the client container where /opt/conf/hive-site.xml points at it.
    """
    database = f"fve_dw_test_{uuid.uuid4().hex[:8]}"
    location = (tmp_path / "dw").as_uri()
    run_file(spark_hive, DDL, DW_DB=database, LAKE_DW=location)
    yield spark_hive, database, location
    spark_hive.sql(f"DROP DATABASE IF EXISTS {database} CASCADE")


def test_ddl_runs_twice(created_warehouse):
    spark, database, location = created_warehouse

    run_file(spark, DDL, DW_DB=database, LAKE_DW=location)

    assert {row.tableName for row in spark.sql(f"SHOW TABLES IN {database}").collect()} == TABLES


def test_all_9_tables_exist(created_warehouse):
    spark, database, _ = created_warehouse

    actual = {row.tableName for row in spark.sql(f"SHOW TABLES IN {database}").collect()}

    assert actual == TABLES


def test_partition_columns(created_warehouse):
    spark, database, _ = created_warehouse

    for table in TABLES:
        expected = PARTITIONS.get(table, [])  # dimensions are unpartitioned
        columns = spark.catalog.listColumns(f"{database}.{table}")
        actual = [column.name for column in columns if column.isPartition]

        assert actual == expected, f"{table}: expected {expected}, got {actual}"


def test_tables_are_external_orc(created_warehouse):
    spark, database, _ = created_warehouse

    for table in TABLES:
        rows = spark.sql(f"DESCRIBE FORMATTED {database}.{table}").collect()

        metadata = {
            str(row[0]).strip().rstrip(":"): str(row[1]).strip() for row in rows if row[0] is not None
        }

        assert metadata.get("Type") == "EXTERNAL"
        assert "OrcInputFormat" in metadata.get("InputFormat", "")
        assert metadata.get("Location", "").rstrip("/").endswith(f"/dw/{table}")
