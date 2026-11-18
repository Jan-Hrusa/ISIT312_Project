"""Tests for the management dashboard drill-down queries."""

import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from warehouse.sql import render, run_file

ROOT = Path(__file__).resolve().parents[2]
DDL = ROOT / "warehouse" / "ddl" / "fve_dw.sql"
SAMPLE = ROOT / "warehouse" / "queries" / "sample_fill.sql"
V3 = ROOT / "warehouse" / "queries" / "v3_category_suppliers.sql"
V4 = ROOT / "warehouse" / "queries" / "v4_supplier_invoices.sql"


@pytest.fixture
def dashboard_sample_warehouse(spark_hive, tmp_path):
    """Create an isolated warehouse containing the dashboard sample data."""
    database = f"fve_dw_dashboard_test_{uuid.uuid4().hex[:8]}"
    location = (tmp_path / "dw").as_uri()

    run_file(spark_hive, DDL, DW_DB=database, LAKE_DW=location)
    run_file(spark_hive, SAMPLE, DW_DB=database)

    yield spark_hive, database

    spark_hive.sql(f"DROP DATABASE IF EXISTS {database} CASCADE")


def test_v3_v4_on_sample(dashboard_sample_warehouse):
    """Check supplier totals and invoice details against hand-computed sample values."""
    spark, database = dashboard_sample_warehouse

    project = "FVE-2026-03"
    category = "PANELS"

    # V3: selected project and category -> supplier totals.
    v3_statement = render(
        V3,
        DW_DB=database,
        project=project,
        category=category,
    )[0]
    suppliers = spark.sql(v3_statement).collect()

    assert len(suppliers) == 1
    supplier = suppliers[0]

    assert supplier.supplier == "Fictional Solar Supplies"
    assert supplier.ico == "10000001"
    assert supplier.invoiced == Decimal("1089.00")
    assert supplier.paid == Decimal("847.00")
    assert supplier.open == Decimal("242.00")
    assert supplier.paid + supplier.open == supplier.invoiced

    # V4: selected project and supplier -> invoice-level details.
    v4_statement = render(
        V4,
        DW_DB=database,
        project=project,
        supplier=supplier.ico,
    )[0]
    invoices = spark.sql(v4_statement).collect()

    assert invoices[0].__fields__ == [
        "invoice_id",
        "invoice_number",
        "issue_date",
        "due_date",
        "gross_amount",
        "payment_status",
        "days_late",
    ]

    actual = [
        (
            row.invoice_id,
            row.invoice_number,
            str(row.issue_date),
            str(row.due_date),
            row.gross_amount,
            row.payment_status,
            row.days_late,
        )
        for row in invoices
    ]

    expected = [
        (
            "10000001-202600006",
            "202600006",
            "2026-02-15",
            "2026-03-01",
            Decimal("242.00"),
            "UNPAID",
            0,
        ),
        (
            "10000001-202500003",
            "202500003",
            "2025-11-15",
            "2025-11-29",
            Decimal("242.00"),
            "PAID",
            0,
        ),
        (
            "10000001-202500006",
            "202500006",
            "2025-12-15",
            "2025-12-29",
            Decimal("302.50"),
            "PAID",
            0,
        ),
        (
            "10000001-202600003",
            "202600003",
            "2026-01-15",
            "2026-01-29",
            Decimal("302.50"),
            "PAID",
            0,
        ),
    ]

    assert actual == expected
    assert len({row.invoice_id for row in invoices}) == 4
    assert sum(row.gross_amount for row in invoices) == supplier.invoiced
