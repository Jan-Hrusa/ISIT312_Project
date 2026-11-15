"""Data-quality checks and deduplication for finance processing (Task 20).

Every function returns issues as a DataFrame with the columns of `common.dq.ISSUE_COLUMNS`, which
`processing.finance.run` unions and writes once with `dq.write_issues(..., job="finance")`.
"""

from __future__ import annotations

from decimal import Decimal

from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from common import dq, schemas

OVERRUN_LIMIT = Decimal("1.15")


def _issues(
    df: DataFrame,
    issue_type: str,
    source: str,
    record_ref: Column,
    detail: Column,
    project_code: Column | None = None,
) -> DataFrame:
    """One issue per row of df, in the column order of dq.ISSUE_COLUMNS."""
    return df.select(
        F.lit(issue_type).alias("issue_type"),
        F.lit(source).alias("source"),
        record_ref.cast("string").alias("record_ref"),
        (project_code if project_code is not None else F.lit(None)).cast("string").alias("project_code"),
        detail.cast("string").alias("detail"),
    )


def dedupe(invoices: DataFrame, lines: DataFrame) -> tuple[DataFrame, DataFrame, DataFrame]:
    """Drop resent copies of an invoice (same supplier and number) and their lines.

    Keeps the copy with the earliest business date (file mtime; a resent copy is later), ties by file name.
    Returns the kept invoices, the kept lines and one DUPLICATE issue per dropped copy (detail = its file).
    The issues carry no project code yet: dedupe runs before project codes exist (see fill_project_codes).
    """
    inv_cols = invoices.columns
    line_cols = lines.columns

    order_cols = [F.col("source_file").asc()]
    if "business_date" in inv_cols:
        order_cols.insert(0, F.col("business_date").asc_nulls_last())

    win = Window.partitionBy("supplier_ico", "number").orderBy(*order_cols)
    ranked = invoices.withColumn("_rn", F.row_number().over(win))

    kept_invoices = ranked.filter(F.col("_rn") == 1).drop("_rn").select(*inv_cols)
    dropped = ranked.filter(F.col("_rn") > 1)
    duplicate_issues = _issues(dropped, "DUPLICATE", "isdoc", F.col("invoice_id"), F.col("source_file"))

    # Lines belong to the copy they were parsed from, so they are kept by invoice and file.
    kept_keys = kept_invoices.select(
        F.col("invoice_id").alias("_k_inv_id"),
        F.col("source_file").alias("_k_src"),
    )
    kept_lines = lines.join(
        kept_keys,
        (lines["invoice_id"] == kept_keys["_k_inv_id"]) & (lines["source_file"] == kept_keys["_k_src"]),
        "inner",
    ).select(*line_cols)

    return kept_invoices, kept_lines, duplicate_issues


def run(
    invoices: DataFrame,
    lines: DataFrame,
    booked: DataFrame,
    budget_lines: DataFrame,
) -> DataFrame:
    """MISSING_VS, NO_PROJECT and OVERRUN issues, after Task 20.1's project_codes.assign."""
    booked_doc_refs = booked.select(F.col("doc_ref").alias("_b_doc_ref")).distinct()
    inv = invoices.join(
        booked_doc_refs, invoices["invoice_id"] == booked_doc_refs["_b_doc_ref"], "left"
    ).withColumn("_has_booking", F.col("_b_doc_ref").isNotNull())

    # Not-yet-booked PDF-only invoices are skipped: their VS is simply not known yet.
    missing_vs = _issues(
        inv.filter(F.col("vs").isNull() & (F.col("has_isdoc") | F.col("_has_booking"))),
        "MISSING_VS",
        "isdoc",
        F.col("invoice_id"),
        F.concat(F.lit("no variable symbol in "), F.col("source_file")),
        F.col("project_code"),
    )

    no_project_booked = _issues(
        booked.filter(F.col("project_code").isNull()).dropDuplicates(["doc_ref"]),
        "NO_PROJECT",
        "accounting",
        F.col("doc_ref"),
        F.concat(F.lit("booked cost without project code in "), F.col("source_file")),
    )

    no_project_invoice = _issues(
        inv.filter((F.col("project_rule") == "NONE") & ~F.col("_has_booking")),
        "NO_PROJECT",
        "isdoc",
        F.col("invoice_id"),
        F.concat(F.lit("no rule assigned a project to the not-yet-booked invoice in "), F.col("source_file")),
    )

    spent = (
        lines.filter(F.col("project_code").isNotNull() & F.col("category").isNotNull())
        .groupBy("project_code", "category")
        .agg(F.sum("amount_net").alias("spent"))
    )
    over = (
        budget_lines.select("project_code", "category", F.col("amount").alias("budget"))
        .join(spent, on=["project_code", "category"], how="inner")
        .filter(F.col("spent") > F.col("budget") * F.lit(OVERRUN_LIMIT))
    )
    overrun = _issues(
        over,
        "OVERRUN",
        "budgets",
        F.concat_ws("/", F.col("project_code"), F.col("category")),
        F.format_string(
            "spent %s CZK vs budget %s CZK (%s%%)",
            F.col("spent").cast(schemas.MONEY).cast("string"),
            F.col("budget").cast(schemas.MONEY).cast("string"),
            F.round(F.col("spent") / F.col("budget") * 100, 1).cast("decimal(8,1)").cast("string"),
        ),
        F.col("project_code"),
    )

    return missing_vs.unionByName(no_project_booked).unionByName(no_project_invoice).unionByName(overrun)


def fill_project_codes(issues: DataFrame, invoices: DataFrame) -> DataFrame:
    """Give DUPLICATE issues the project code of the invoice copy that was kept.

    Called after project_codes.assign; other issues keep their project code (NULL where none is known).
    """
    codes = invoices.select(F.col("invoice_id").alias("_f_id"), F.col("project_code").alias("_f_code"))
    return (
        issues.join(
            codes,
            (issues["issue_type"] == "DUPLICATE") & (issues["record_ref"] == codes["_f_id"]),
            "left",
        )
        .withColumn("project_code", F.coalesce(F.col("project_code"), F.col("_f_code")))
        .select(*dq.ISSUE_COLUMNS)
    )
