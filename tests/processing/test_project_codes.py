"""Unit tests for project code assignment (Task 20.1)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from processing.finance import (
    BOOKED_COSTS_SCHEMA,
    INVOICE_LINES_WORK_SCHEMA,
    INVOICES_WORK_SCHEMA,
    PROJECTS_SCHEMA,
    SUPPLIERS_SCHEMA,
    project_codes,
)


def _make_base_dfs(spark, invoices_data, lines_data, booked_data, projects_data=None, suppliers_data=None):
    inv_df = spark.createDataFrame(invoices_data, schema=INVOICES_WORK_SCHEMA)
    ln_df = spark.createDataFrame(lines_data, schema=INVOICE_LINES_WORK_SCHEMA)
    bk_df = spark.createDataFrame(booked_data, schema=BOOKED_COSTS_SCHEMA)
    pr_df = spark.createDataFrame(projects_data or [], schema=PROJECTS_SCHEMA)
    sp_df = spark.createDataFrame(suppliers_data or [], schema=SUPPLIERS_SCHEMA)
    return inv_df, ln_df, bk_df, pr_df, sp_df


def test_pdf_only_completed_from_booking(spark) -> None:
    inv_row = {
        "invoice_id": "26100001-FV01",
        "supplier_ico": "26100001",
        "number": "FV01",
        "vs": None,
        "issue_date": None,
        "due_date": None,
        "total_net": None,
        "total_vat": None,
        "total_gross": None,
        "currency": "CZK",
        "category": None,
        "project_code": None,
        "project_rule": None,
        "has_isdoc": False,
        "source_file": "/raw/isdoc/26100001_FV01.pdf",
        "business_date": date(2025, 3, 10),
    }
    booked_row = {
        "doc_ref": "26100001-FV01",
        "supplier_ico": "26100001",
        "vs": "202501",
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "booking_date": date(2025, 3, 2),
        "project_code": "FVE-2025-01",
        "cost_centre": "CC1",
        "category": "PANELS",
        "amount": Decimal("1000.00"),
        "amount_gross": Decimal("1210.00"),
        "export_week": "2025-W10",
        "source_file": "/raw/accounting/money_export_2025-W10.csv",
    }
    inv_df, ln_df, bk_df, pr_df, sp_df = _make_base_dfs(
        spark, [inv_row], [], [booked_row]
    )
    out_inv, out_ln = project_codes.assign(inv_df, ln_df, bk_df, pr_df, sp_df)

    res_inv = out_inv.collect()[0]
    assert res_inv["vs"] == "202501"
    assert res_inv["issue_date"] == date(2025, 3, 1)
    assert res_inv["total_net"] == Decimal("1000.00")
    assert res_inv["project_code"] == "FVE-2025-01"
    assert res_inv["project_rule"] == "BOOKED"

    res_ln = out_ln.collect()
    assert len(res_ln) == 1
    assert res_ln[0]["description"] == "booked from PDF"


def test_project_code_from_booked_cost(spark) -> None:
    inv_row = {
        "invoice_id": "26100001-FV02",
        "supplier_ico": "26100001",
        "number": "FV02",
        "vs": "202",
        "issue_date": date(2025, 3, 5),
        "due_date": date(2025, 3, 20),
        "total_net": Decimal("500.00"),
        "total_vat": Decimal("105.00"),
        "total_gross": Decimal("605.00"),
        "currency": "CZK",
        "category": None,
        "project_code": None,
        "project_rule": None,
        "has_isdoc": True,
        "source_file": "/raw/isdoc/26100001_FV02.isdoc",
        "business_date": date(2025, 3, 5),
    }
    booked_row = {
        "doc_ref": "26100001-FV02",
        "supplier_ico": "26100001",
        "vs": "202",
        "issue_date": date(2025, 3, 5),
        "due_date": date(2025, 3, 20),
        "booking_date": date(2025, 3, 6),
        "project_code": "FVE-2025-02",
        "cost_centre": "CC2",
        "category": "INVERTERS",
        "amount": Decimal("500.00"),
        "amount_gross": Decimal("605.00"),
        "export_week": "2025-W10",
        "source_file": "/raw/accounting/money_export_2025-W10.csv",
    }
    inv_df, ln_df, bk_df, pr_df, sp_df = _make_base_dfs(
        spark, [inv_row], [], [booked_row]
    )
    out_inv, _ = project_codes.assign(inv_df, ln_df, bk_df, pr_df, sp_df)
    r = out_inv.collect()[0]
    assert r["project_code"] == "FVE-2025-02"
    assert r["project_rule"] == "BOOKED"
    assert r["category"] == "INVERTERS"


def test_project_code_fallback_single_active_project(spark) -> None:
    inv_booked = {
        "invoice_id": "26100001-FV01",
        "supplier_ico": "26100001",
        "number": "FV01",
        "vs": "101",
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
        "source_file": "/raw/isdoc/1.isdoc",
        "business_date": date(2025, 3, 1),
    }
    inv_unbooked = {
        **inv_booked,
        "invoice_id": "26100001-FV02",
        "number": "FV02",
        "issue_date": date(2025, 4, 1),
        "source_file": "/raw/isdoc/2.isdoc",
    }
    booked_row = {
        "doc_ref": "26100001-FV01",
        "supplier_ico": "26100001",
        "vs": "101",
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "booking_date": date(2025, 3, 2),
        "project_code": "FVE-2025-01",
        "cost_centre": "CC1",
        "category": "PANELS",
        "amount": Decimal("100.00"),
        "amount_gross": Decimal("121.00"),
        "export_week": "2025-W10",
        "source_file": "/raw/accounting/m.csv",
    }
    proj_row = {
        "project_code": "FVE-2025-01",
        "name": "P1",
        "town": "Brno",
        "region": "JMK",
        "lat": 49.0,
        "lon": 16.0,
        "radius_m": 100,
        "mwp": Decimal("1.00"),
        "has_battery": False,
        "contract_value": Decimal("10000.00"),
        "offer_date": date(2025, 1, 1),
        "signed_date": date(2025, 1, 15),
        "construction_start": date(2025, 2, 1),
        "construction_end": date(2025, 6, 1),
        "status": "ACTIVE",
        "source_file": "/raw/master/projects.csv",
    }
    inv_df, ln_df, bk_df, pr_df, sp_df = _make_base_dfs(
        spark, [inv_booked, inv_unbooked], [], [booked_row], [proj_row]
    )
    out_inv, _ = project_codes.assign(inv_df, ln_df, bk_df, pr_df, sp_df)
    res = {r["invoice_id"]: r for r in out_inv.collect()}
    assert res["26100001-FV02"]["project_code"] == "FVE-2025-01"
    assert res["26100001-FV02"]["project_rule"] == "SINGLE_ACTIVE"


def test_two_active_projects_gives_none(spark) -> None:
    inv1 = {
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
        "source_file": "1.isdoc",
        "business_date": date(2025, 3, 1),
    }
    inv2 = {**inv1, "invoice_id": "26100001-FV02", "number": "FV02", "source_file": "2.isdoc"}
    inv_target = {**inv1, "invoice_id": "26100001-FV03", "number": "FV03", "source_file": "3.isdoc"}

    b1 = {
        "doc_ref": "26100001-FV01",
        "supplier_ico": "26100001",
        "vs": "1",
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "booking_date": date(2025, 3, 2),
        "project_code": "FVE-2025-01",
        "cost_centre": "CC",
        "category": "PANELS",
        "amount": Decimal("100.00"),
        "amount_gross": Decimal("121.00"),
        "export_week": "2025-W10",
        "source_file": "m.csv",
    }
    b2 = {**b1, "doc_ref": "26100001-FV02", "project_code": "FVE-2025-02"}

    p1 = {
        "project_code": "FVE-2025-01",
        "name": "P1",
        "town": "T",
        "region": "R",
        "lat": 49.0,
        "lon": 16.0,
        "radius_m": 100,
        "mwp": Decimal("1.00"),
        "has_battery": False,
        "contract_value": Decimal("1000.00"),
        "offer_date": date(2025, 1, 1),
        "signed_date": date(2025, 1, 10),
        "construction_start": date(2025, 2, 1),
        "construction_end": date(2025, 6, 1),
        "status": "ACTIVE",
        "source_file": "p.csv",
    }
    p2 = {**p1, "project_code": "FVE-2025-02"}

    inv_df, ln_df, bk_df, pr_df, sp_df = _make_base_dfs(
        spark, [inv1, inv2, inv_target], [], [b1, b2], [p1, p2]
    )
    out_inv, _ = project_codes.assign(inv_df, ln_df, bk_df, pr_df, sp_df)
    res = {r["invoice_id"]: r for r in out_inv.collect()}
    assert res["26100001-FV03"]["project_code"] is None
    assert res["26100001-FV03"]["project_rule"] == "NONE"


def test_category_falls_back_to_supplier(spark) -> None:
    inv = {
        "invoice_id": "26100001-FV99",
        "supplier_ico": "26100001",
        "number": "FV99",
        "vs": "99",
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
        "source_file": "99.isdoc",
        "business_date": date(2025, 3, 1),
    }
    supp = {
        "ico": "26100001",
        "name": "Solar s.r.o.",
        "category": "CABLES",
        "bank_account": "123456",
        "bank_code": "0100",
        "source_file": "s.csv",
    }
    inv_df, ln_df, bk_df, pr_df, sp_df = _make_base_dfs(
        spark, [inv], [], [], [], [supp]
    )
    out_inv, _ = project_codes.assign(inv_df, ln_df, bk_df, pr_df, sp_df)
    r = out_inv.collect()[0]
    assert r["category"] == "CABLES"


def test_lines_inherit_code(spark) -> None:
    inv = {
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
        "source_file": "1.isdoc",
        "business_date": date(2025, 3, 1),
    }
    ln = {
        "invoice_id": "26100001-FV01",
        "line_no": 1,
        "description": "Item",
        "quantity": Decimal("1.000"),
        "unit_price": Decimal("100.00"),
        "amount_net": Decimal("100.00"),
        "vat_rate": Decimal("21.00"),
        "vat_amount": Decimal("21.00"),
        "category": None,
        "project_code": None,
        "source_file": "1.isdoc",
        "business_date": date(2025, 3, 1),
    }
    bk = {
        "doc_ref": "26100001-FV01",
        "supplier_ico": "26100001",
        "vs": "1",
        "issue_date": date(2025, 3, 1),
        "due_date": date(2025, 3, 15),
        "booking_date": date(2025, 3, 2),
        "project_code": "FVE-2025-01",
        "cost_centre": "CC",
        "category": "PANELS",
        "amount": Decimal("100.00"),
        "amount_gross": Decimal("121.00"),
        "export_week": "2025-W10",
        "source_file": "m.csv",
    }
    inv_df, ln_df, bk_df, pr_df, sp_df = _make_base_dfs(
        spark, [inv], [ln], [bk]
    )
    _, out_ln = project_codes.assign(inv_df, ln_df, bk_df, pr_df, sp_df)
    res_ln = out_ln.collect()[0]
    assert res_ln["project_code"] == "FVE-2025-01"
    assert res_ln["category"] == "PANELS"
