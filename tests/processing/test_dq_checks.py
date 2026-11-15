"""Unit tests for data-quality checks and deduplication (Task 20)."""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from common import config
from processing.finance import (
    BOOKED_COSTS_SCHEMA,
    BUDGET_LINES_SCHEMA,
    INVOICE_LINES_WORK_SCHEMA,
    INVOICES_WORK_SCHEMA,
    dq_checks,
)


def test_duplicate_keeps_first_copy(spark) -> None:
    inv_early = {
        "invoice_id": "26100001-FV01",
        "supplier_ico": "26100001",
        "number": "FV01",
        "vs": "1",
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "total_net": Decimal("100.00"),
        "total_vat": Decimal("21.00"),
        "total_gross": Decimal("121.00"),
        "currency": "CZK",
        "category": None,
        "project_code": None,
        "project_rule": None,
        "has_isdoc": True,
        "source_file": "/raw/isdoc/copy_a.isdoc",
        "business_date": date(2025, 3, 1),
    }
    inv_late = {
        **inv_early,
        "source_file": "/raw/isdoc/copy_b.isdoc",
        "business_date": date(2025, 3, 5),
    }
    ln_early = {
        "invoice_id": "26100001-FV01",
        "line_no": 1,
        "description": "Early",
        "quantity": Decimal("1.000"),
        "unit_price": Decimal("100.00"),
        "amount_net": Decimal("100.00"),
        "vat_rate": Decimal("21.00"),
        "vat_amount": Decimal("21.00"),
        "category": None,
        "project_code": None,
        "source_file": "/raw/isdoc/copy_a.isdoc",
        "business_date": date(2025, 3, 1),
    }
    ln_late = {**ln_early, "description": "Late", "source_file": "/raw/isdoc/copy_b.isdoc"}

    inv_df = spark.createDataFrame([inv_late, inv_early], schema=INVOICES_WORK_SCHEMA)
    ln_df = spark.createDataFrame([ln_late, ln_early], schema=INVOICE_LINES_WORK_SCHEMA)

    kept_inv, kept_ln, dup_issues = dq_checks.dedupe(inv_df, ln_df)
    assert kept_inv.count() == 1
    assert kept_inv.collect()[0]["source_file"] == "/raw/isdoc/copy_a.isdoc"
    assert kept_ln.count() == 1
    assert len(dup_issues) == 1
    assert dup_issues[0]["issue_type"] == "DUPLICATE"
    assert dup_issues[0]["detail"] == "/raw/isdoc/copy_b.isdoc"


def test_overrun_threshold_is_115_percent(spark) -> None:
    budgets_data = [
        {
            "project_code": "FVE-2025-01",
            "category": "PANELS",
            "amount": Decimal("1000.00"),
            "source_file": "b.xlsx",
        },
        {
            "project_code": "FVE-2025-01",
            "category": "INVERTERS",
            "amount": Decimal("1000.00"),
            "source_file": "b.xlsx",
        },
    ]
    lines_data = [
        {
            "invoice_id": "26100001-FV01",
            "line_no": 1,
            "description": "115.0%",
            "quantity": Decimal("1.000"),
            "unit_price": Decimal("1150.00"),
            "amount_net": Decimal("1150.00"),
            "vat_rate": Decimal("21.00"),
            "vat_amount": Decimal("241.50"),
            "category": "PANELS",
            "project_code": "FVE-2025-01",
            "source_file": "1.isdoc",
            "business_date": date(2025, 3, 1),
        },
        {
            "invoice_id": "26100001-FV02",
            "line_no": 1,
            "description": "115.1%",
            "quantity": Decimal("1.000"),
            "unit_price": Decimal("1151.00"),
            "amount_net": Decimal("1151.00"),
            "vat_rate": Decimal("21.00"),
            "vat_amount": Decimal("241.71"),
            "category": "INVERTERS",
            "project_code": "FVE-2025-01",
            "source_file": "2.isdoc",
            "business_date": date(2025, 3, 1),
        },
    ]
    inv_df = spark.createDataFrame([], schema=INVOICES_WORK_SCHEMA)
    ln_df = spark.createDataFrame(lines_data, schema=INVOICE_LINES_WORK_SCHEMA)
    bk_df = spark.createDataFrame([], schema=BOOKED_COSTS_SCHEMA)
    bg_df = spark.createDataFrame(budgets_data, schema=BUDGET_LINES_SCHEMA)

    issues = dq_checks.run(inv_df, ln_df, bk_df, bg_df)
    overruns = [i for i in issues if i["issue_type"] == "OVERRUN"]
    assert len(overruns) == 1
    assert overruns[0]["record_ref"] == "FVE-2025-01/INVERTERS"


def test_each_issue_type_found(spark) -> None:
    inv_base = {
        "invoice_id": "26100001-FV01",
        "supplier_ico": "26100001",
        "number": "FV01",
        "vs": None,
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "total_net": Decimal("1200.00"),
        "total_vat": Decimal("252.00"),
        "total_gross": Decimal("1452.00"),
        "currency": "CZK",
        "category": "PANELS",
        "project_code": "FVE-2025-01",
        "project_rule": "BOOKED",
        "has_isdoc": True,
        "source_file": "/raw/isdoc/a.isdoc",
        "business_date": date(2025, 3, 1),
    }
    inv_dup = {**inv_base, "source_file": "/raw/isdoc/b.isdoc", "business_date": date(2025, 3, 2)}
    inv_no_proj = {
        **inv_base,
        "invoice_id": "26100001-FV02",
        "number": "FV02",
        "vs": "202",
        "project_code": None,
        "project_rule": "NONE",
        "source_file": "/raw/isdoc/c.isdoc",
    }
    ln_row = {
        "invoice_id": "26100001-FV01",
        "line_no": 1,
        "description": "Line",
        "quantity": Decimal("1.000"),
        "unit_price": Decimal("1200.00"),
        "amount_net": Decimal("1200.00"),
        "vat_rate": Decimal("21.00"),
        "vat_amount": Decimal("252.00"),
        "category": "PANELS",
        "project_code": "FVE-2025-01",
        "source_file": "/raw/isdoc/a.isdoc",
        "business_date": date(2025, 3, 1),
    }
    bk_no_proj = {
        "doc_ref": "26100001-FV99",
        "supplier_ico": "26100001",
        "vs": "99",
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "booking_date": date(2025, 3, 2),
        "project_code": None,
        "cost_centre": "CC",
        "category": "PANELS",
        "amount": Decimal("100.00"),
        "amount_gross": Decimal("121.00"),
        "export_week": "2025-W10",
        "source_file": "m.csv",
    }
    bg_row = {
        "project_code": "FVE-2025-01",
        "category": "PANELS",
        "amount": Decimal("1000.00"),
        "source_file": "b.xlsx",
    }

    inv_df = spark.createDataFrame([inv_base, inv_dup, inv_no_proj], schema=INVOICES_WORK_SCHEMA)
    ln_df = spark.createDataFrame([ln_row], schema=INVOICE_LINES_WORK_SCHEMA)
    bk_df = spark.createDataFrame([bk_no_proj], schema=BOOKED_COSTS_SCHEMA)
    bg_df = spark.createDataFrame([bg_row], schema=BUDGET_LINES_SCHEMA)

    dedup_inv, dedup_ln, dup_issues = dq_checks.dedupe(inv_df, ln_df)
    other_issues = dq_checks.run(dedup_inv, dedup_ln, bk_df, bg_df)
    all_found = {(i["issue_type"], i["source"]) for i in (dup_issues + other_issues)}

    assert ("DUPLICATE", "isdoc") in all_found
    assert ("MISSING_VS", "isdoc") in all_found
    assert ("NO_PROJECT", "accounting") in all_found
    assert ("NO_PROJECT", "isdoc") in all_found
    assert ("OVERRUN", "budgets") in all_found
