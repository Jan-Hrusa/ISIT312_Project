import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest

from common import config
from common.schemas import CLEAN_PARTITIONS, CLEAN_TABLES, TABLE_WRITERS, column_names
from common.tables import create_table_sql, read_table, write_table

HIVE_TYPE = re.compile(r"STRING|INT|BIGINT|DOUBLE|BOOLEAN|DATE|TIMESTAMP|DECIMAL\(\d+,\d+\)|ARRAY<STRING>")
CONTRACTS = Path(__file__).resolve().parents[2] / "docs" / "contracts.md"


def test_every_table_has_columns_and_types():
    assert len(CLEAN_TABLES) == 14
    assert set(TABLE_WRITERS) == set(CLEAN_TABLES)
    for table, columns in CLEAN_TABLES.items():
        names = [name for name, _ in columns]
        assert names, table
        assert len(names) == len(set(names)), f"duplicate column in {table}"
        for name, hive_type in columns:
            assert re.fullmatch(r"[a-z][a-z0-9_]*", name), (table, name)
            assert HIVE_TYPE.fullmatch(hive_type), (table, name, hive_type)
            if name in ("amount", "paid_amount", "contract_value") or name.startswith("total_"):
                assert hive_type == "DECIMAL(14,2)", (table, name)
            if name.endswith("_date") or name == "as_of":
                assert hive_type == "DATE", (table, name)
    assert CLEAN_PARTITIONS == {"dq_issues": [("job", "STRING")]}


def test_create_table_sql_is_external_orc():
    sql = create_table_sql("dq_issues")
    assert sql.startswith(f"CREATE EXTERNAL TABLE IF NOT EXISTS {config.CLEAN_DB}.dq_issues (")
    assert "PARTITIONED BY (`job` STRING)" in sql
    assert "STORED AS ORC" in sql
    assert sql.endswith(f"LOCATION '{config.LAKE_CLEAN}/dq_issues'")


def test_contracts_doc_lists_every_column():
    text = CONTRACTS.read_text(encoding="utf-8")
    for table, columns in CLEAN_TABLES.items():
        row = next((line for line in text.splitlines() if line.startswith(f"| `{table}` |")), None)
        assert row is not None, f"docs/contracts.md has no row for {table}"
        cell = row.split("|")[2].split("; partitioned by")[0]
        listed = re.findall(r"`([a-z0-9_]+)` ([A-Z]+(?:\(\d+,\d+\)|<STRING>)?)", cell)
        assert listed == columns, f"docs/contracts.md row for {table} differs from common/schemas.py"


def _invoice_rows(spark):
    # Columns shuffled, numbers and dates as strings, plus one column the contract doesn't have.
    return spark.createDataFrame(
        [
            ("12345678-2026001", "isdoc", "2026-11-02", "1000.5", "12345678", "2026001"),
            ("87654321-77", "isdoc", "2026-10-15", "20", "87654321", "77"),
        ],
        ["invoice_id", "extra", "issue_date", "total_net", "supplier_ico", "number"],
    ).selectExpr(
        "*",
        "'2026-11-30' AS due_date",
        "CAST(NULL AS STRING) AS vs",
        "total_net * 0.21 AS total_vat",
        "total_net * 1.21 AS total_gross",
        "'CZK' AS currency",
        "'PANELS' AS category",
        "'FVE-2026-02' AS project_code",
        "'BOOKED' AS project_rule",
        "true AS has_isdoc",
        "'/lake/raw/isdoc/2026/11/x__20261114093000.isdoc' AS source_file",
    )


def test_write_table_orders_and_casts(clean_db):
    spark = clean_db
    write_table(spark, _invoice_rows(spark), "invoices")
    out = read_table(spark, "invoices")
    assert out.columns == column_names("invoices")
    types = dict(out.dtypes)
    assert types["issue_date"] == "date"
    assert types["total_net"] == "decimal(14,2)"
    assert types["has_isdoc"] == "boolean"
    row = out.where("invoice_id = '12345678-2026001'").first()
    assert row.issue_date == dt.date(2026, 11, 2)
    assert row.total_net == Decimal("1000.50")
    assert row.vs is None

    # Overwrite: a second write replaces the table's content.
    write_table(spark, _invoice_rows(spark).limit(1), "invoices")
    assert read_table(spark, "invoices").count() == 1


def test_write_table_rejects_missing_column(clean_db):
    spark = clean_db
    df = _invoice_rows(spark).drop("vs", "currency")
    with pytest.raises(ValueError, match="missing columns for invoices: vs, currency"):
        write_table(spark, df, "invoices")


def test_write_table_refuses_tables_with_own_writer(clean_db):
    df = clean_db.createDataFrame([("x",)], ["run_id"])
    with pytest.raises(ValueError, match="append only"):
        write_table(clean_db, df, "ingest_log")
    with pytest.raises(ValueError, match="write_issues"):
        write_table(clean_db, df, "dq_issues")
    with pytest.raises(ValueError, match="unknown table: nope"):
        write_table(clean_db, df, "nope")
