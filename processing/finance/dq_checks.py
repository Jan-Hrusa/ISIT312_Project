"""Data-quality checks and deduplication for finance processing (Task 20)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def _make_issue(
    issue_type: str,
    source: str,
    record_ref: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "detected_at": datetime.now(timezone.utc),
        "job": "finance",
        "source": source,
        "issue_type": issue_type,
        "record_ref": record_ref,
        "detail": detail,
    }


def dedupe(
    invoices: DataFrame, lines: DataFrame
) -> tuple[DataFrame, DataFrame, list[dict[str, Any]]]:
    """Deduplicate invoices with the same supplier_ico and number (invoice_id)."""
    inv_cols = invoices.columns
    line_cols = lines.columns

    has_bdate = "business_date" in inv_cols
    order_cols = (
        [F.col("business_date").asc_nulls_last(), F.col("source_file").asc()]
        if has_bdate
        else [F.col("source_file").asc()]
    )

    win = Window.partitionBy("supplier_ico", "number").orderBy(*order_cols)
    ranked = invoices.withColumn("_rn", F.row_number().over(win))

    kept_invoices = ranked.filter(F.col("_rn") == 1).drop("_rn").select(*inv_cols)
    dropped_invoices = ranked.filter(F.col("_rn") > 1).select(
        "invoice_id", "source_file"
    )

    duplicate_issues: list[dict[str, Any]] = []
    for row in dropped_invoices.orderBy("invoice_id", "source_file").collect():
        duplicate_issues.append(
            _make_issue(
                issue_type="DUPLICATE",
                source="isdoc",
                record_ref=row["invoice_id"],
                detail=row["source_file"],
            )
        )

    kept_keys = kept_invoices.select(
        F.col("invoice_id").alias("_k_inv_id"),
        F.col("source_file").alias("_k_src"),
    )
    kept_lines = (
        lines.join(
            kept_keys,
            (lines["invoice_id"] == kept_keys["_k_inv_id"])
            & (lines["source_file"] == kept_keys["_k_src"]),
            "inner",
        )
        .select(*line_cols)
    )

    return kept_invoices, kept_lines, duplicate_issues


def run(
    invoices: DataFrame,
    lines: DataFrame,
    booked: DataFrame,
    budget_lines: DataFrame,
) -> list[dict[str, Any]]:
    """Run finance data-quality checks after Task 20.1 project_codes.assign."""
    issues: list[dict[str, Any]] = []

    booked_doc_refs = booked.select(
        F.col("doc_ref").alias("_b_doc_ref")
    ).distinct()

    inv_with_booking_flag = invoices.join(
        booked_doc_refs,
        invoices["invoice_id"] == booked_doc_refs["_b_doc_ref"],
        "left",
    ).withColumn("_has_booking", F.col("_b_doc_ref").isNotNull())

    missing_vs_rows = (
        inv_with_booking_flag.filter(
            F.col("vs").isNull() & (F.col("has_isdoc") | F.col("_has_booking"))
        )
        .select("invoice_id", "source_file")
        .orderBy("invoice_id")
        .collect()
    )
    for r in missing_vs_rows:
        issues.append(
            _make_issue(
                issue_type="MISSING_VS",
                source="isdoc",
                record_ref=r["invoice_id"],
                detail=f"Missing variable symbol in {r['source_file']}",
            )
        )

    no_proj_booked_rows = (
        booked.filter(F.col("project_code").isNull())
        .select("doc_ref", "source_file")
        .dropDuplicates(["doc_ref"])
        .orderBy("doc_ref")
        .collect()
    )
    for r in no_proj_booked_rows:
        issues.append(
            _make_issue(
                issue_type="NO_PROJECT",
                source="accounting",
                record_ref=r["doc_ref"],
                detail=f"Booked cost has no project_code in {r['source_file']}",
            )
        )

    no_proj_inv_rows = (
        inv_with_booking_flag.filter(
            (F.col("project_rule") == "NONE")
            & (~F.col("_has_booking"))
            & F.col("has_isdoc")
        )
        .select("invoice_id", "source_file")
        .orderBy("invoice_id")
        .collect()
    )
    for r in no_proj_inv_rows:
        issues.append(
            _make_issue(
                issue_type="NO_PROJECT",
                source="isdoc",
                record_ref=r["invoice_id"],
                detail=f"No project assigned to unbooked invoice in {r['source_file']}",
            )
        )

    spent_df = (
        lines.filter(
            F.col("project_code").isNotNull() & F.col("category").isNotNull()
        )
        .groupBy("project_code", "category")
        .agg(F.sum("amount_net").alias("spent"))
    )

    overrun_rows = (
        budget_lines.select(
            F.col("project_code"),
            F.col("category"),
            F.col("amount").alias("budget_amount"),
        )
        .join(spent_df, on=["project_code", "category"], how="inner")
        .filter(
            F.col("spent") > (F.col("budget_amount") * F.lit(Decimal("1.15")))
        )
        .orderBy("project_code", "category")
        .collect()
    )

    for r in overrun_rows:
        spent_val = Decimal(str(r["spent"])).quantize(Decimal("0.01"))
        budget_val = Decimal(str(r["budget_amount"])).quantize(Decimal("0.01"))
        pct = (spent_val / budget_val * Decimal("100")).quantize(Decimal("0.1"))
        issues.append(
            _make_issue(
                issue_type="OVERRUN",
                source="budgets",
                record_ref=f"{r['project_code']}/{r['category']}",
                detail=f"Spent {spent_val} CZK vs budget {budget_val} CZK ({pct}%)",
            )
        )

    return issues
