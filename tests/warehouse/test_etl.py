"""Tests for Task 26: Warehouse loads and checks."""

from pathlib import Path

import pytest

from common import tables
from processing.finance import run as run_finance


def fixture_inputs(root: Path) -> dict[str, list[str]]:
    """Locate the existing synthetic finance source files."""
    return {
        "master": [
            (root / "master/projects.csv").as_uri(),
            (root / "master/suppliers.csv").as_uri(),
        ],
        "budgets": [p.as_uri() for p in sorted((root / "drive/budgets").glob("*.xlsx"))],
        "isdoc": [p.as_uri() for p in sorted((root / "mailbox/invoices").glob("*.isdoc"))],
        "invoice_pdf": [p.as_uri() for p in sorted((root / "mailbox/invoices").glob("*.pdf"))],
        "accounting": [p.as_uri() for p in sorted((root / "drive/accounting").glob("*.csv"))],
    }


@pytest.fixture
def finance_data(clean_db, sources_tree: Path):
    """Populate clean-zone finance tables from existing fixtures."""
    counts = run_finance(clean_db, inputs=fixture_inputs(sources_tree))

    assert counts["projects"] == 3
    assert counts["suppliers"] == 5
    assert counts["budget_lines"] == 10
    assert counts["invoices"] == 4

    return clean_db


@pytest.fixture
def bank_data(finance_data):
    """Add synthetic bank transactions for warehouse testing."""
    from common.schemas import CLEAN_TABLES

    spark = finance_data

    rows = [
        {
            "tx_id": "TX001",
            "bank": "RB",
            "account": "2101234567",
            "statement_no": 1,
            "statement_date": "2026-05-22",
            "line_no": 1,
            "value_date": "2026-05-22",
            "amount": "-145200.00",
            "counterparty_account": "1234509876",
            "counterparty_bank_code": "2010",
            "vs": "202600014",
            "ks": None,
            "ss": None,
            "note": "Invoice payment",
            "source_file": "synthetic_bank.csv",
        },
        {
            "tx_id": "TX002",
            "bank": "RB",
            "account": "2101234567",
            "statement_no": 1,
            "statement_date": "2026-05-22",
            "line_no": 2,
            "value_date": "2026-05-22",
            "amount": "5000.00",
            "counterparty_account": None,
            "counterparty_bank_code": None,
            "vs": None,
            "ks": None,
            "ss": None,
            "note": "Incoming transfer",
            "source_file": "synthetic_bank.csv",
        },
    ]

    columns = [name for name, _ in CLEAN_TABLES["bank_transactions"]]
    from pyspark.sql.types import StructField, StructType, _parse_datatype_string

    schema = StructType(
        [
            StructField(name, _parse_datatype_string(dtype), True)
            for name, dtype in CLEAN_TABLES["bank_transactions"]
        ]
    )

    from datetime import date
    from decimal import Decimal

    for row in rows:
        row["statement_date"] = date.fromisoformat(row["statement_date"])
        row["value_date"] = date.fromisoformat(row["value_date"])
        row["amount"] = Decimal(row["amount"])

    df = spark.createDataFrame(
        [tuple(row[name] for name in columns) for row in rows],
        schema,
    )
    tables.write_table(spark, df, "bank_transactions")

    return spark


@pytest.fixture
def payment_data(bank_data):
    """Add synthetic invoice matching and payment status."""
    from common.schemas import CLEAN_TABLES

    spark = bank_data

    rows = [
        {
            "invoice_id": "20400013-202600014",
            "status": "PAID",
            "paid_amount": "145200.00",
            "paid_date": "2026-05-22",
            "days_to_pay": 18,
            "days_late": 0,
            "order_ids": ["ORD001"],
            "uncleared_order_ids": [],
            "tx_ids": ["TX001"],
            "as_of": "2026-05-30",
        }
    ]

    columns = [name for name, _ in CLEAN_TABLES["invoice_status"]]
    from datetime import date
    from decimal import Decimal

    from pyspark.sql.types import StructField, StructType, _parse_datatype_string

    schema = StructType(
        [
            StructField(name, _parse_datatype_string(dtype), True)
            for name, dtype in CLEAN_TABLES["invoice_status"]
        ]
    )

    for row in rows:
        row["paid_amount"] = Decimal(row["paid_amount"])
        row["paid_date"] = date.fromisoformat(row["paid_date"])
        row["as_of"] = date.fromisoformat(row["as_of"])

    df = spark.createDataFrame(
        [tuple(row[name] for name in columns) for row in rows],
        schema,
    )
    tables.write_table(spark, df, "invoice_status")

    return spark


@pytest.fixture
def warehouse_data(payment_data):
    """Add a payment order and return Spark with test data."""
    from common.schemas import CLEAN_TABLES

    spark = payment_data

    row = {
        "order_id": "ORD001",
        "bank": "RB",
        "account": "2101234567",
        "order_date": "2026-05-20",
        "due_date": "2026-05-22",
        "amount": "145200.00",
        "counterparty_account": "1234509876",
        "counterparty_bank_code": "2010",
        "vs": "202600014",
        "ks": None,
        "ss": None,
        "source_file": "synthetic_orders.csv",
    }

    columns = [name for name, _ in CLEAN_TABLES["payment_orders"]]
    from datetime import date
    from decimal import Decimal

    from pyspark.sql.types import StructField, StructType, _parse_datatype_string

    schema = StructType(
        [
            StructField(name, _parse_datatype_string(dtype), True)
            for name, dtype in CLEAN_TABLES["payment_orders"]
        ]
    )

    row["order_date"] = date.fromisoformat(row["order_date"])
    row["due_date"] = date.fromisoformat(row["due_date"])
    row["amount"] = Decimal(row["amount"])

    df = spark.createDataFrame(
        [tuple(row[name] for name in columns)],
        schema,
    )
    tables.write_table(spark, df, "payment_orders")

    return spark


def test_unknown_project_row(warehouse_data, monkeypatch, tmp_path):
    """The project dimension must include the UNKNOWN member."""
    from common import config
    from warehouse.sql import run_file

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_unknown")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    run_file(spark, Path("warehouse/ddl/fve_dw.sql"))
    run_file(spark, Path("warehouse/etl/load_dims.sql"))

    unknown = spark.sql(f"SELECT * FROM {config.DW_DB}.dim_project WHERE project_key = -1").collect()

    assert len(unknown) == 1
    assert unknown[0]["project_code"] == "UNKNOWN"


def test_payment_amount_positive(warehouse_data, monkeypatch, tmp_path):
    """Only debit transactions become positive warehouse payments."""
    from decimal import Decimal

    from common import config
    from warehouse.sql import run_file

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_payment")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    run_file(spark, Path("warehouse/ddl/fve_dw.sql"))
    run_file(spark, Path("warehouse/etl/load_dims.sql"))
    run_file(spark, Path("warehouse/etl/load_facts.sql"))

    payments = spark.table(f"{config.DW_DB}.fact_payment").collect()

    assert len(payments) == 1
    assert payments[0]["tx_id"] == "TX001"
    assert payments[0]["amount"] == Decimal("145200.00")


def test_checks_pass_on_fixture(warehouse_data, monkeypatch, tmp_path):
    """All five warehouse checks must pass on valid fixture data."""
    from common import config
    from warehouse.etl.run import run

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_checks")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    counts = run(spark)

    assert counts["checks_failed"] == 0
    assert counts["dim_project"] == 4
    assert counts["dim_supplier"] == 6
    assert counts["dim_cost_category"] == 10
    assert counts["fact_budget_line"] == 10
    assert counts["fact_payment"] == 1
    assert counts["fact_payment_order"] == 1


def test_loads_are_idempotent(warehouse_data, monkeypatch, tmp_path):
    """Running warehouse ETL twice must produce identical row counts."""
    from common import config
    from warehouse.etl.run import run

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_idempotent")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    first_counts = run(spark)
    second_counts = run(spark)

    assert first_counts == second_counts
    assert second_counts["checks_failed"] == 0


def _rewrite_clean_table(spark, table: str, change) -> None:
    """Overwrite a clean table with `change(rows)`; rows are collected first (Spark can't overwrite input)."""
    from common import config

    current = spark.table(f"{config.CLEAN_DB}.{table}")
    schema = current.schema
    rows = [row.asDict() for row in current.collect()]
    new_rows = change(rows)
    df = spark.createDataFrame([tuple(r[f.name] for f in schema.fields) for r in new_rows], schema)
    tables.write_table(spark, df, table)


def test_check_fails_on_broken_fixture(warehouse_data, monkeypatch, tmp_path):
    """A line lost on the way (its invoice is missing, so the load's join drops it) fails the run."""
    from common import config
    from warehouse.etl.run import run

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_broken")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    def add_orphan_line(rows):
        orphan = dict(rows[0], invoice_id="99999999-NOINVOICE", line_no=1)
        return rows + [orphan]

    _rewrite_clean_table(spark, "invoice_lines", add_orphan_line)

    with pytest.raises(RuntimeError, match="warehouse checks failed: invoice_amount_check"):
        run(spark)


def test_duplicate_payment_fails_unique_check(warehouse_data, monkeypatch, tmp_path):
    """A transaction loaded twice fails the uniqueness check."""
    from common import config
    from warehouse.etl.run import run
    from warehouse.sql import named_queries

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_duplicate")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    run(spark)

    payment = spark.table(f"{config.DW_DB}.fact_payment").first()
    assert payment is not None

    spark.sql(f"""
        INSERT INTO {config.DW_DB}.fact_payment
        PARTITION (pay_year=2026, pay_month=5)
        VALUES (
            '{payment.tx_id}', {payment.account_key},
            {payment.date_key}, {payment.supplier_key},
            '{payment.invoice_id}', {payment.project_key},
            {payment.amount}, {payment.days_late}
        )
    """)

    checks = named_queries(Path("warehouse/etl/checks.sql"))
    failures = []

    for name, query in checks.items():
        result = spark.sql(query).first()
        if result["ok"] is not True:
            failures.append(name)

    # the copy also breaks the row count against the bank debits
    assert failures == ["payment_count_check", "payment_tx_unique_check"]


def test_order_cleared_flags(warehouse_data, monkeypatch, tmp_path):
    """cleared = 1 for a matched order, 0 for an uncleared one, NULL for an order matching no invoice."""
    from common import config
    from warehouse.sql import run_file

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_cleared")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    def add_uncleared(rows):
        return [dict(r, order_ids=["ORD001", "ORD002"], uncleared_order_ids=["ORD002"]) for r in rows]

    def add_orders(rows):
        return rows + [dict(rows[0], order_id="ORD002"), dict(rows[0], order_id="ORD003")]

    _rewrite_clean_table(spark, "invoice_status", add_uncleared)
    _rewrite_clean_table(spark, "payment_orders", add_orders)

    run_file(spark, Path("warehouse/ddl/fve_dw.sql"))
    run_file(spark, Path("warehouse/etl/load_dims.sql"))
    run_file(spark, Path("warehouse/etl/load_facts.sql"))

    rows = spark.table(f"{config.DW_DB}.fact_payment_order").collect()
    cleared = {r["order_id"]: r["cleared"] for r in rows}

    assert len(rows) == 3
    assert cleared == {"ORD001": 1, "ORD002": 0, "ORD003": None}
    assert {r["order_id"]: r["invoice_id"] for r in rows}["ORD003"] is None


def test_iso_week_format(warehouse_data, monkeypatch, tmp_path):
    """dim_date.iso_week is the ISO week-year and week as YYYY-Www (contracts section 8)."""
    from common import config
    from warehouse.sql import run_file

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_iso_week")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    run_file(spark, Path("warehouse/ddl/fve_dw.sql"))
    run_file(spark, Path("warehouse/etl/load_dims.sql"))

    weeks = {
        r["date_key"]: r["iso_week"]
        for r in spark.sql(
            f"SELECT date_key, iso_week FROM {config.DW_DB}.dim_date "
            "WHERE date_key IN (20160101, 20210104, 20261102, 20261231)"
        ).collect()
    }

    assert weeks == {20160101: "2015-W53", 20210104: "2021-W01", 20261102: "2026-W45", 20261231: "2026-W53"}


def test_static_dimensions_match_config(warehouse_data, monkeypatch, tmp_path):
    """The VALUES lists in load_dims.sql equal common/config CATEGORIES and BANKS; keys follow the codes."""
    from common import config
    from warehouse.sql import run_file

    spark = warehouse_data

    monkeypatch.setattr(config, "DW_DB", "fve_dw_test_static")
    monkeypatch.setattr(config, "LAKE_DW", (tmp_path / "warehouse").as_uri())

    run_file(spark, Path("warehouse/ddl/fve_dw.sql"))
    run_file(spark, Path("warehouse/etl/load_dims.sql"))

    categories = spark.table(f"{config.DW_DB}.dim_cost_category").orderBy("category_key").collect()
    assert {
        r["category_code"]: (r["category_name"], r["group_name"]) for r in categories
    } == config.CATEGORIES
    assert [r["category_code"] for r in categories] == sorted(config.CATEGORIES)
    assert [r["category_key"] for r in categories] == list(range(1, len(config.CATEGORIES) + 1))

    accounts = spark.table(f"{config.DW_DB}.dim_bank_account").orderBy("account_key").collect()
    assert {r["bank"]: (r["bank_name"], r["bank_code"], r["account"], r["currency"]) for r in accounts} == {
        code: (b.name, b.bank_code, b.account, config.CURRENCY) for code, b in config.BANKS.items()
    }
    assert [r["account"] for r in accounts] == sorted(b.account for b in config.BANKS.values())


def test_runner_rejects_failed_checks():
    """The runner raises RuntimeError when a warehouse check fails."""
    from unittest.mock import MagicMock, patch

    from warehouse.etl.run import run

    spark = MagicMock()
    spark.sql.return_value.collect.return_value = [
        {
            "check_name": "payment_tx_unique_check",
            "ok": False,
            "detail": "duplicate transaction ID",
        }
    ]

    with (
        patch("warehouse.etl.run.run_file"),
        patch(
            "warehouse.etl.run.named_queries",
            return_value={"payment_tx_unique_check": "SELECT broken_check"},
        ),
    ):
        with pytest.raises(
            RuntimeError,
            match="warehouse checks failed: payment_tx_unique_check",
        ):
            run(spark)
