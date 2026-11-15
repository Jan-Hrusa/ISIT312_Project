"""Project code assignment and PDF-only invoice completion (Task 20.1)."""

from __future__ import annotations

from decimal import Decimal
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window

DEC_14_2 = T.DecimalType(14, 2)
DEC_14_3 = T.DecimalType(14, 3)
DEC_5_2 = T.DecimalType(5, 2)


def assign(
    invoices: DataFrame,
    lines: DataFrame,
    booked: DataFrame,
    projects: DataFrame,
    suppliers: DataFrame,
) -> tuple[DataFrame, DataFrame]:
    """Assign project codes and categories to invoices and lines using Spark DataFrames."""
    invoice_cols = invoices.columns
    line_cols = lines.columns

    booked_win = Window.partitionBy("doc_ref").orderBy(
        F.col("export_week").asc_nulls_last(), F.col("source_file").asc_nulls_last()
    )
    booked_dedup = (
        booked.withColumn("_rn", F.row_number().over(booked_win))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )

    b_ref = booked_dedup.select(
        F.col("doc_ref").alias("_b_doc_ref"),
        F.col("vs").alias("_b_vs"),
        F.col("issue_date").alias("_b_issue_date"),
        F.col("due_date").alias("_b_due_date"),
        F.col("amount").cast(DEC_14_2).alias("_b_net"),
        F.col("amount_gross").cast(DEC_14_2).alias("_b_gross"),
        F.col("project_code").alias("_b_project_code"),
        F.col("category").alias("_b_category"),
    )

    # 0. Complete PDF-only invoices (has_isdoc = false) from booked_costs
    inv_b = invoices.join(
        b_ref, invoices["invoice_id"] == b_ref["_b_doc_ref"], "left"
    )
    is_booked_pdf = (~F.col("has_isdoc")) & F.col("_b_doc_ref").isNotNull()

    completed_inv = (
        inv_b.withColumn(
            "vs", F.when(is_booked_pdf, F.col("_b_vs")).otherwise(F.col("vs"))
        )
        .withColumn(
            "issue_date",
            F.when(is_booked_pdf, F.col("_b_issue_date")).otherwise(F.col("issue_date")),
        )
        .withColumn(
            "due_date",
            F.when(is_booked_pdf, F.col("_b_due_date")).otherwise(F.col("due_date")),
        )
        .withColumn(
            "total_net",
            F.when(is_booked_pdf, F.col("_b_net")).otherwise(F.col("total_net")),
        )
        .withColumn(
            "total_gross",
            F.when(is_booked_pdf, F.col("_b_gross")).otherwise(F.col("total_gross")),
        )
        .withColumn(
            "total_vat",
            F.when(
                is_booked_pdf, (F.col("_b_gross") - F.col("_b_net")).cast(DEC_14_2)
            ).otherwise(F.col("total_vat")),
        )
    )

    synth_lines = completed_inv.filter(is_booked_pdf).select(
        F.col("invoice_id"),
        F.lit(1).cast(T.IntegerType()).alias("line_no"),
        F.lit("booked from PDF").alias("description"),
        F.lit(Decimal("1.000")).cast(DEC_14_3).alias("quantity"),
        F.col("total_net").cast(DEC_14_2).alias("unit_price"),
        F.col("total_net").cast(DEC_14_2).alias("amount_net"),
        F.lit(Decimal("21.00")).cast(DEC_5_2).alias("vat_rate"),
        F.col("total_vat").cast(DEC_14_2).alias("vat_amount"),
        F.lit(None).cast(T.StringType()).alias("category"),
        F.lit(None).cast(T.StringType()).alias("project_code"),
        F.col("source_file"),
    )
    for extra_col in line_cols:
        if extra_col not in synth_lines.columns:
            synth_lines = synth_lines.withColumn(extra_col, F.lit(None))
    synth_lines = synth_lines.select(*line_cols)

    booked_pdf_ids = completed_inv.filter(is_booked_pdf).select("invoice_id")
    base_lines = lines.join(
        booked_pdf_ids, on="invoice_id", how="left_anti"
    ).unionByName(synth_lines)

    # 1 & 2. Pool of supplier's BOOKED invoices for SINGLE_ACTIVE fallback
    booked_invoices_pool = (
        completed_inv.filter(
            F.col("_b_project_code").isNotNull() & F.col("issue_date").isNotNull()
        )
        .select(
            F.col("supplier_ico").alias("_pool_ico"),
            F.col("issue_date").alias("_pool_issue_date"),
            F.col("_b_project_code").alias("_pool_project_code"),
        )
        .distinct()
    )

    proj_active = projects.select(
        F.col("project_code").alias("_p_code"),
        F.col("signed_date").alias("_p_signed"),
        F.col("construction_start").alias("_p_start"),
        F.col("construction_end").alias("_p_end"),
    )

    candidates = (
        completed_inv.select("invoice_id", "supplier_ico", "issue_date")
        .filter(F.col("issue_date").isNotNull())
        .join(
            booked_invoices_pool,
            (F.col("supplier_ico") == F.col("_pool_ico"))
            & F.col("_pool_issue_date").between(
                F.date_sub(F.col("issue_date"), 90),
                F.date_add(F.col("issue_date"), 90),
            ),
            "inner",
        )
        .join(
            proj_active,
            (F.col("_pool_project_code") == F.col("_p_code"))
            & F.col("_p_signed").isNotNull()
            & F.col("_p_start").isNotNull()
            & F.col("_p_end").isNotNull()
            & (F.col("_p_start") <= F.col("issue_date"))
            & (F.col("issue_date") <= F.col("_p_end")),
            "inner",
        )
        .groupBy("invoice_id")
        .agg(
            F.countDistinct("_p_code").alias("_active_cnt"),
            F.first("_p_code").alias("_single_project_code"),
        )
    )

    supp_ref = suppliers.select(
        F.col("ico").alias("_s_ico"),
        F.col("category").alias("_s_category"),
    ).dropDuplicates(["_s_ico"])

    assigned_inv = (
        completed_inv.join(candidates, on="invoice_id", how="left")
        .join(supp_ref, completed_inv["supplier_ico"] == supp_ref["_s_ico"], how="left")
        .withColumn(
            "project_rule",
            F.when(F.col("_b_project_code").isNotNull(), F.lit("BOOKED"))
            .when(F.col("_active_cnt") == 1, F.lit("SINGLE_ACTIVE"))
            .otherwise(F.lit("NONE")),
        )
        .withColumn(
            "project_code",
            F.when(F.col("_b_project_code").isNotNull(), F.col("_b_project_code"))
            .when(F.col("_active_cnt") == 1, F.col("_single_project_code"))
            .otherwise(F.lit(None).cast(T.StringType())),
        )
        .withColumn(
            "category",
            F.coalesce(F.col("_b_category"), F.col("_s_category")),
        )
        .select(*invoice_cols)
    )

    inv_meta = assigned_inv.select(
        F.col("invoice_id"),
        F.col("project_code").alias("_inv_project_code"),
        F.col("category").alias("_inv_category"),
    )

    assigned_lines = (
        base_lines.join(inv_meta, on="invoice_id", how="left")
        .withColumn("project_code", F.col("_inv_project_code"))
        .withColumn("category", F.col("_inv_category"))
        .select(*line_cols)
    )

    return assigned_inv, assigned_lines
