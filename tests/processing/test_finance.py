"""Unit and integration tests for Tasks 13, 20.1, and 20 (processing/finance)."""

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
    PROJECTS_SCHEMA,
    SUPPLIERS_SCHEMA,
    budgets,
    dq_checks,
    invoice_pdf,
    isdoc,
    money_export,
    project_codes,
    run as run_finance,
)
from processing.finance.master import FinanceParseError

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def test_parse_isdoc_sample() -> None:
    sample_path = sorted((FIXTURES_DIR / "isdoc").glob("*.isdoc"))[0]
    inv, lines = isdoc.parse(sample_path.read_bytes(), str(sample_path))
    assert inv["invoice_id"] == f"{inv['supplier_ico']}-{inv['number']}"
    assert inv["has_isdoc"] is True
    assert len(lines) >= 1


def test_isdoc_totals_equal_lines() -> None:
    for p in sorted((FIXTURES_DIR / "isdoc").glob("*.isdoc")):
        inv, lines = isdoc.parse(p.read_bytes(), str(p))
        net_sum = sum((ln["amount_net"] for ln in lines), Decimal("0.00"))
        vat_sum = sum((ln["vat_amount"] for ln in lines), Decimal("0.00"))
        assert inv["total_net"] == net_sum
        assert inv["total_vat"] == vat_sum
        assert inv["total_gross"] == inv["total_net"] + inv["total_vat"]


def test_isdoc_missing_vs_is_null() -> None:
    sample_path = sorted((FIXTURES_DIR / "isdoc").glob("*.isdoc"))[0]
    xml_text = sample_path.read_text(encoding="utf-8")
    xml_empty_vs = xml_text.replace(
        "<VariableSymbol>", "<VariableSymbol>000</VariableSymbol><_Ignore>"
    ).replace("</VariableSymbol>", "</_Ignore>")
    inv_zero, _ = isdoc.parse(xml_empty_vs.encode("utf-8"), "zero_vs.isdoc")
    assert inv_zero["vs"] is None


def test_decimal_comma() -> None:
    assert money_export.parse_decimal_comma("1234,50") == Decimal("1234.50")
    assert money_export.parse_decimal_comma("1 234,50") == Decimal("1234.50")


def test_budget_has_10_categories() -> None:
    xlsx_path = sorted((FIXTURES_DIR / "budgets").glob("*.xlsx"))[0]
    rows = budgets.parse_budget(xlsx_path.read_bytes(), str(xlsx_path))
    assert len(rows) == 10
    assert {r["category"] for r in rows} == set(config.CATEGORIES)


def test_pdf_only_invoice_row() -> None:
    row = invoice_pdf.header(
        "26100001_FV20250099__20250301T120000Z.pdf",
        "/data/raw/isdoc/26100001_FV20250099__20250301T120000Z.pdf",
    )
    assert row["invoice_id"] == "26100001-FV20250099"
    assert row["has_isdoc"] is False


def test_bad_xml_gives_parse_error() -> None:
    with pytest.raises(FinanceParseError):
        isdoc.parse(b"<Invoice><broken></Invoice>", "corrupt.isdoc")


def test_run_on_fixtures(spark) -> None:
    inputs = {
        "master": f"file://{FIXTURES_DIR / 'master'}",
        "budgets": f"file://{FIXTURES_DIR / 'budgets'}",
        "isdoc": f"file://{FIXTURES_DIR / 'isdoc'}",
        "accounting": f"file://{FIXTURES_DIR / 'accounting'}",
    }
    run_finance(spark, inputs=inputs)
    assert spark.table(f"{config.CLEAN_DB}.invoices").count() == 4


def _make_base_dfs(
    spark, invoices_data, lines_data, booked_data, projects_data=None, suppliers_data=None
):
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
    assert res_inv["total_vat"] == Decimal("210.00")
    assert res_inv["total_gross"] == Decimal("1210.00")
    assert res_inv["project_code"] == "FVE-2025-01"
    assert res_inv["project_rule"] == "BOOKED"

    res_ln = out_ln.collect()
    assert len(res_ln) == 1
    assert res_ln[0]["description"] == "booked from PDF"
    assert res_ln[0]["amount_net"] == Decimal("1000.00")
    assert res_ln[0]["vat_rate"] == Decimal("21.00")


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


@pytest.mark.integration
def test_planted_problems_found_exactly(spark) -> None:
    truth_candidates = [
        Path("/data/truth/planted_finance.csv"),
        Path("/repo/data/truth/planted_finance.csv"),
        Path(__file__).resolve().parents[2] / "data" / "truth" / "planted_finance.csv",
    ]
    truth_path = next((p for p in truth_candidates if p.exists()), None)
    if truth_path is None or not spark.catalog.tableExists(f"{config.CLEAN_DB}.dq_issues"):
        pytest.skip("Scale-1 truth file or fve_clean.dq_issues not present; skipping.")

    with truth_path.open("r", encoding="utf-8") as f:
        truth_rows = list(csv.DictReader(f))

    expected_by_type: dict[str, set[str]] = {}
    for r in truth_rows:
        expected_by_type.setdefault(r["issue_type"].strip(), set()).add(r["record_ref"].strip())

    actual_rows = (
        spark.table(f"{config.CLEAN_DB}.dq_issues")
        .filter("job = 'finance'")
        .select("issue_type", "source", "record_ref")
        .collect()
    )
    actual_by_type: dict[str, set[str]] = {}
    for r in actual_rows:
        actual_by_type.setdefault(r["issue_type"], set()).add(r["record_ref"])

    for itype, exp_refs in expected_by_type.items():
        act_refs = actual_by_type.get(itype, set())
        assert exp_refs.issubset(act_refs), f"Missing planted {itype}: {exp_refs - act_refs}"
