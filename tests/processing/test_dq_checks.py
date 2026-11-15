"""Unit tests for data-quality checks and deduplication (Task 20), plus the planted-problem check."""

from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import PurePosixPath

import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import DateType, StringType

from common import config, dq, lake, tables
from common.spark import get_spark
from processing.finance import _spark_schema, dq_checks

# The frames processing.finance.run hands to the checks: contract columns plus the working columns it keeps.
INVOICES_WORK_SCHEMA = _spark_schema("invoices", [("business_date", DateType())])
INVOICE_LINES_WORK_SCHEMA = _spark_schema(
    "invoice_lines", [("source_file", StringType()), ("business_date", DateType())]
)
BOOKED_COSTS_SCHEMA = _spark_schema("booked_costs")
BUDGET_LINES_SCHEMA = _spark_schema("budget_lines")

INV_BASE = {
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
LINE_BASE = {
    "invoice_id": "26100001-FV01",
    "line_no": 1,
    "description": "Line",
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
BOOKED_BASE = {
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


def _frames(spark, invoices=(), lines=(), booked=(), budgets=()):
    return (
        spark.createDataFrame(list(invoices), schema=INVOICES_WORK_SCHEMA),
        spark.createDataFrame(list(lines), schema=INVOICE_LINES_WORK_SCHEMA),
        spark.createDataFrame(list(booked), schema=BOOKED_COSTS_SCHEMA),
        spark.createDataFrame(list(budgets), schema=BUDGET_LINES_SCHEMA),
    )


def test_duplicate_keeps_first_copy(spark) -> None:
    inv_late = {**INV_BASE, "source_file": "/raw/isdoc/copy_b.isdoc", "business_date": date(2025, 3, 5)}
    ln_early = {**LINE_BASE, "description": "Early"}
    ln_late = {**LINE_BASE, "description": "Late", "source_file": "/raw/isdoc/copy_b.isdoc"}
    inv_df, ln_df, _, _ = _frames(spark, [inv_late, INV_BASE], [ln_late, ln_early])

    kept_inv, kept_ln, dup_issues = dq_checks.dedupe(inv_df, ln_df)

    assert [r["source_file"] for r in kept_inv.collect()] == ["/raw/isdoc/copy_a.isdoc"]
    assert [r["description"] for r in kept_ln.collect()] == ["Early"]
    rows = dup_issues.collect()
    assert len(rows) == 1
    assert (rows[0]["issue_type"], rows[0]["source"], rows[0]["record_ref"]) == (
        "DUPLICATE",
        "isdoc",
        "26100001-FV01",
    )
    assert rows[0]["detail"] == "/raw/isdoc/copy_b.isdoc"


def test_overrun_threshold_is_115_percent(spark) -> None:
    budgets = [
        {
            "project_code": "FVE-2025-01",
            "category": cat,
            "amount": Decimal("1000.00"),
            "source_file": "b.xlsx",
        }
        for cat in ("PANELS", "INVERTERS")
    ]
    lines = [
        {**LINE_BASE, "invoice_id": "26100001-FV01", "amount_net": Decimal("1150.00"), "category": "PANELS"},
        {
            **LINE_BASE,
            "invoice_id": "26100001-FV02",
            "amount_net": Decimal("1151.00"),
            "category": "INVERTERS",
        },
    ]
    lines = [{**ln, "project_code": "FVE-2025-01"} for ln in lines]
    inv_df, ln_df, bk_df, bg_df = _frames(spark, lines=lines, budgets=budgets)

    overruns = dq_checks.run(inv_df, ln_df, bk_df, bg_df).filter("issue_type = 'OVERRUN'").collect()

    assert len(overruns) == 1
    assert overruns[0]["record_ref"] == "FVE-2025-01/INVERTERS"
    assert overruns[0]["project_code"] == "FVE-2025-01"
    assert overruns[0]["detail"] == "spent 1151.00 CZK vs budget 1000.00 CZK (115.1%)"


def test_each_issue_type_found(spark) -> None:
    inv_base = {
        **INV_BASE,
        "vs": None,
        "total_net": Decimal("1200.00"),
        "category": "PANELS",
        "project_code": "FVE-2025-01",
        "project_rule": "BOOKED",
        "source_file": "/raw/isdoc/a.isdoc",
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
        **LINE_BASE,
        "amount_net": Decimal("1200.00"),
        "category": "PANELS",
        "project_code": "FVE-2025-01",
        "source_file": "/raw/isdoc/a.isdoc",
    }
    bg_row = {
        "project_code": "FVE-2025-01",
        "category": "PANELS",
        "amount": Decimal("1000.00"),
        "source_file": "b",
    }
    inv_df, ln_df, bk_df, bg_df = _frames(
        spark, [inv_base, inv_dup, inv_no_proj], [ln_row], [BOOKED_BASE], [bg_row]
    )

    dedup_inv, dedup_ln, dup_issues = dq_checks.dedupe(inv_df, ln_df)
    other_issues = dq_checks.run(dedup_inv, dedup_ln, bk_df, bg_df)
    all_found = {(r["issue_type"], r["source"]) for r in dup_issues.unionByName(other_issues).collect()}

    assert all_found == {
        ("DUPLICATE", "isdoc"),
        ("MISSING_VS", "isdoc"),
        ("NO_PROJECT", "accounting"),
        ("NO_PROJECT", "isdoc"),
        ("OVERRUN", "budgets"),
    }


def test_unbooked_pdf_only_invoice_gives_no_project(spark) -> None:
    pdf_only = {
        **INV_BASE,
        "vs": None,
        "issue_date": None,
        "due_date": None,
        "total_net": None,
        "total_vat": None,
        "total_gross": None,
        "project_rule": "NONE",
        "has_isdoc": False,
        "source_file": "/raw/invoice_pdf/26100001_FV01.pdf",
    }
    inv_df, ln_df, bk_df, bg_df = _frames(spark, [pdf_only])

    found = {(r["issue_type"], r["source"]) for r in dq_checks.run(inv_df, ln_df, bk_df, bg_df).collect()}

    # NO_PROJECT as the task's rule says; no MISSING_VS, the VS of an unbooked PDF is not known yet.
    assert found == {("NO_PROJECT", "isdoc")}


def test_issues_have_dq_columns_and_project_codes(spark) -> None:
    inv_late = {
        **INV_BASE,
        "vs": None,
        "source_file": "/raw/isdoc/copy_b.isdoc",
        "business_date": date(2025, 3, 5),
    }
    inv_df, ln_df, bk_df, bg_df = _frames(spark, [inv_late, {**INV_BASE, "vs": None}], [LINE_BASE])

    kept_inv, kept_ln, dup_issues = dq_checks.dedupe(inv_df, ln_df)
    # What project_codes.assign would give the kept copy.
    kept_inv = kept_inv.withColumn("project_code", F.lit("FVE-2025-01"))
    check_issues = dq_checks.run(kept_inv, kept_ln, bk_df, bg_df)
    issues = dq_checks.fill_project_codes(dup_issues.unionByName(check_issues), kept_inv)

    for frame in (dup_issues, check_issues, issues):
        assert tuple(frame.columns) == dq.ISSUE_COLUMNS
    by_type = {r["issue_type"]: r["project_code"] for r in issues.collect()}
    assert by_type == {"DUPLICATE": "FVE-2025-01", "MISSING_VS": "FVE-2025-01"}


def _invoice_id_from_path(path: str) -> str:
    """`.../<ico>_<number>__<ingest ts>.isdoc` or `<ico>_<number>.pdf` -> `<ico>-<number>`."""
    stem = PurePosixPath(path).stem.split("__", 1)[0]
    return stem.replace("_", "-", 1)


@pytest.mark.integration
def test_planted_problems_found_exactly(_spark_sessions) -> None:
    truth_path = config.LEDGER_DIR / "planted_finance.csv"
    if not truth_path.exists():
        pytest.skip(f"no truth file {truth_path}: generate the scale-1 data and run the pipeline first")
    _spark_sessions.stop()  # this test reads the stack's metastore, not a test one
    spark = get_spark("test-planted-finance")
    try:
        if not spark.catalog.tableExists(tables.qualified_name("dq_issues")):
            pytest.skip("no dq_issues table: run the pipeline (collect, finance) first")
        issues = tables.read_table(spark, "dq_issues").filter("job = 'finance'").collect()
        if not issues:
            pytest.skip("no finance issues: run the finance step first")

        truth = list(csv.DictReader(truth_path.open(encoding="utf-8")))
        expected = {(r["problem"], r["ref"]) for r in truth}

        def ref(row) -> str:
            return (
                _invoice_id_from_path(row["record_ref"])
                if row["issue_type"] == "PARSE_ERROR"
                else row["record_ref"]
            )

        actual = {(r["issue_type"], ref(r)): r for r in issues}
        missing = expected - set(actual)
        assert not missing, f"planted problems not found: {sorted(missing)}"

        invoices = tables.read_table(spark, "invoices")
        single_cells = {
            (r["project_code"], r["category"])
            for r in invoices.filter("project_rule = 'SINGLE_ACTIVE'")
            .select("project_code", "category")
            .collect()
        }
        file_dates = {
            _invoice_id_from_path(r["original_path"]): r["business_date"]
            for source in ("isdoc", "invoice_pdf")
            for r in lake.current_raw_files(spark, source).select("original_path", "business_date").collect()
        }
        recent = config.DATA_END - timedelta(days=14)

        not_allowed = []
        for key in sorted(set(actual) - expected):
            row = actual[key]
            if row["issue_type"] == "NO_PROJECT" and row["source"] == "isdoc":
                file_date = file_dates.get(row["record_ref"])
                if file_date is not None and file_date > recent:
                    continue  # not booked yet: normal in the last 14 days
            if row["issue_type"] == "OVERRUN":
                project_code, category = row["record_ref"].split("/", 1)
                if (project_code, category) in single_cells:
                    continue  # the SINGLE_ACTIVE fallback can put an unbooked invoice on this project
            not_allowed.append(key)
        assert not not_allowed, f"issues that were not planted: {not_allowed}"
    finally:
        spark.stop()
