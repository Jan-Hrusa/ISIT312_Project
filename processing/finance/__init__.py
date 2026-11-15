"""Spark job for finance processing (Tasks 13, 20.1, 20)."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import types as T

from common import config
from common.dq import write_issues
from common.raw_files import current_raw_files
from processing.finance import (
    budgets,
    dq_checks,
    invoice_pdf,
    isdoc,
    master,
    money_export,
    project_codes,
)
from processing.finance.master import FinanceParseError

PROJECTS_SCHEMA = T.StructType(
    [
        T.StructField("project_code", T.StringType(), True),
        T.StructField("name", T.StringType(), True),
        T.StructField("town", T.StringType(), True),
        T.StructField("region", T.StringType(), True),
        T.StructField("lat", T.DoubleType(), True),
        T.StructField("lon", T.DoubleType(), True),
        T.StructField("radius_m", T.IntegerType(), True),
        T.StructField("mwp", T.DecimalType(6, 2), True),
        T.StructField("has_battery", T.BooleanType(), True),
        T.StructField("contract_value", T.DecimalType(14, 2), True),
        T.StructField("offer_date", T.DateType(), True),
        T.StructField("signed_date", T.DateType(), True),
        T.StructField("construction_start", T.DateType(), True),
        T.StructField("construction_end", T.DateType(), True),
        T.StructField("status", T.StringType(), True),
        T.StructField("source_file", T.StringType(), True),
    ]
)

SUPPLIERS_SCHEMA = T.StructType(
    [
        T.StructField("ico", T.StringType(), True),
        T.StructField("name", T.StringType(), True),
        T.StructField("category", T.StringType(), True),
        T.StructField("bank_account", T.StringType(), True),
        T.StructField("bank_code", T.StringType(), True),
        T.StructField("source_file", T.StringType(), True),
    ]
)

BUDGET_LINES_SCHEMA = T.StructType(
    [
        T.StructField("project_code", T.StringType(), True),
        T.StructField("category", T.StringType(), True),
        T.StructField("amount", T.DecimalType(14, 2), True),
        T.StructField("source_file", T.StringType(), True),
    ]
)

INVOICES_WORK_SCHEMA = T.StructType(
    [
        T.StructField("invoice_id", T.StringType(), True),
        T.StructField("supplier_ico", T.StringType(), True),
        T.StructField("number", T.StringType(), True),
        T.StructField("vs", T.StringType(), True),
        T.StructField("issue_date", T.DateType(), True),
        T.StructField("due_date", T.DateType(), True),
        T.StructField("total_net", T.DecimalType(14, 2), True),
        T.StructField("total_vat", T.DecimalType(14, 2), True),
        T.StructField("total_gross", T.DecimalType(14, 2), True),
        T.StructField("currency", T.StringType(), True),
        T.StructField("category", T.StringType(), True),
        T.StructField("project_code", T.StringType(), True),
        T.StructField("project_rule", T.StringType(), True),
        T.StructField("has_isdoc", T.BooleanType(), True),
        T.StructField("source_file", T.StringType(), True),
        T.StructField("business_date", T.DateType(), True),
    ]
)

INVOICE_LINES_WORK_SCHEMA = T.StructType(
    [
        T.StructField("invoice_id", T.StringType(), True),
        T.StructField("line_no", T.IntegerType(), True),
        T.StructField("description", T.StringType(), True),
        T.StructField("quantity", T.DecimalType(14, 3), True),
        T.StructField("unit_price", T.DecimalType(14, 2), True),
        T.StructField("amount_net", T.DecimalType(14, 2), True),
        T.StructField("vat_rate", T.DecimalType(5, 2), True),
        T.StructField("vat_amount", T.DecimalType(14, 2), True),
        T.StructField("category", T.StringType(), True),
        T.StructField("project_code", T.StringType(), True),
        T.StructField("source_file", T.StringType(), True),
        T.StructField("business_date", T.DateType(), True),
    ]
)

BOOKED_COSTS_SCHEMA = T.StructType(
    [
        T.StructField("doc_ref", T.StringType(), True),
        T.StructField("supplier_ico", T.StringType(), True),
        T.StructField("vs", T.StringType(), True),
        T.StructField("issue_date", T.DateType(), True),
        T.StructField("due_date", T.DateType(), True),
        T.StructField("booking_date", T.DateType(), True),
        T.StructField("project_code", T.StringType(), True),
        T.StructField("cost_centre", T.StringType(), True),
        T.StructField("category", T.StringType(), True),
        T.StructField("amount", T.DecimalType(14, 2), True),
        T.StructField("amount_gross", T.DecimalType(14, 2), True),
        T.StructField("export_week", T.StringType(), True),
        T.StructField("source_file", T.StringType(), True),
    ]
)

CLEAN_TABLE_COLS: dict[str, list[str]] = {
    "projects": [f.name for f in PROJECTS_SCHEMA.fields],
    "suppliers": [f.name for f in SUPPLIERS_SCHEMA.fields],
    "budget_lines": [f.name for f in BUDGET_LINES_SCHEMA.fields],
    "invoices": [
        f.name for f in INVOICES_WORK_SCHEMA.fields if f.name != "business_date"
    ],
    "invoice_lines": [
        f.name for f in INVOICE_LINES_WORK_SCHEMA.fields if f.name != "business_date"
    ],
    "booked_costs": [f.name for f in BOOKED_COSTS_SCHEMA.fields],
}

_FS_PREFIX_RE = re.compile(r"^hdfs://[^/]+")


def _strip_fs_prefix(uri: str) -> str:
    if uri.startswith("hdfs://"):
        return _FS_PREFIX_RE.sub("", uri)
    if uri.startswith("file:"):
        parsed = urlparse(uri)
        path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        return path
    return uri


def _original_name(raw_path: str) -> str:
    p = PurePosixPath(raw_path.replace("\\", "/"))
    stem = p.stem
    if "__" in stem:
        stem = stem.split("__", 1)[0]
    return f"{stem}{p.suffix}"


def _read_source_files(
    spark: SparkSession, source: str, override_uri: str | None
) -> list[tuple[str, str, date | None, bytes]]:
    sc = spark.sparkContext

    if override_uri is None:
        raw_df = current_raw_files(spark, source)
        meta_rows = raw_df.select("raw_path", "original_name", "business_date").collect()
        if not meta_rows:
            return []
        meta_by_path: dict[str, tuple[str, date | None]] = {
            _strip_fs_prefix(r["raw_path"]): (r["original_name"], r["business_date"])
            for r in meta_rows
        }
        target_dir = f"{config.HDFS_RAW}/{source}"
        pairs = sc.binaryFiles(target_dir).collect()
        results: list[tuple[str, str, date | None, bytes]] = []
        for full_uri, payload in pairs:
            norm = _strip_fs_prefix(full_uri)
            if norm in meta_by_path:
                orig_name, bdate = meta_by_path[norm]
                results.append((norm, orig_name, bdate, bytes(payload)))
        results.sort(key=lambda item: item[0])
        return results

    parsed = urlparse(override_uri)
    if parsed.scheme in ("", "file"):
        local_path = unquote(parsed.path) if parsed.scheme == "file" else override_uri
        if re.match(r"^/[A-Za-z]:/", local_path):
            local_path = local_path[1:]
        p = Path(local_path)
        if p.exists():
            files = [p] if p.is_file() else sorted(x for x in p.iterdir() if x.is_file())
            out: list[tuple[str, str, date | None, bytes]] = []
            for f in files:
                if f.name.startswith("."):
                    continue
                mtime_date = datetime.fromtimestamp(
                    os.path.getmtime(f), tz=timezone.utc
                ).date()
                raw_p = f.as_posix()
                out.append((raw_p, _original_name(raw_p), mtime_date, f.read_bytes()))
            return out

    pairs = sc.binaryFiles(override_uri).collect()
    results = []
    for full_uri, payload in sorted(pairs, key=lambda x: x[0]):
        raw_p = _strip_fs_prefix(full_uri)
        results.append((raw_p, _original_name(raw_p), None, bytes(payload)))
    return results


def _write_clean_table(spark: SparkSession, table: str, df: DataFrame) -> None:
    cols = CLEAN_TABLE_COLS[table]
    clean_df = df.select(*cols)
    full_name = f"{config.CLEAN_DB}.{table}"
    spark.sql(f"CREATE DATABASE IF NOT EXISTS {config.CLEAN_DB}")
    if spark.catalog.tableExists(full_name):
        target_cols = [c.name for c in spark.catalog.listColumns(full_name)]
        clean_df.select(*target_cols).write.mode("overwrite").insertInto(full_name)
    else:
        clean_df.write.mode("overwrite").saveAsTable(full_name)


def run(spark: SparkSession, inputs: dict[str, str] | None = None) -> None:
    """Execute the complete finance pipeline (Tasks 13, 20.1, 20)."""
    inputs = inputs or {}
    parse_issues: list[dict[str, Any]] = []

    def record_parse_error(source: str, raw_path: str, exc: Exception) -> None:
        parse_issues.append(
            {
                "detected_at": datetime.now(timezone.utc),
                "job": "finance",
                "source": source,
                "issue_type": "PARSE_ERROR",
                "record_ref": raw_path,
                "detail": str(exc),
            }
        )

    project_rows: list[dict[str, Any]] = []
    supplier_rows: list[dict[str, Any]] = []
    for raw_path, orig_name, _bdate, payload in _read_source_files(
        spark, "master", inputs.get("master")
    ):
        low = orig_name.lower()
        try:
            text = payload.decode("utf-8")
            if low == "projects.csv":
                project_rows.extend(master.parse_projects(text, raw_path))
            elif low == "suppliers.csv":
                supplier_rows.extend(master.parse_suppliers(text, raw_path))
        except (UnicodeDecodeError, FinanceParseError) as exc:
            record_parse_error("master", raw_path, exc)

    budget_rows: list[dict[str, Any]] = []
    for raw_path, orig_name, _bdate, payload in _read_source_files(
        spark, "budgets", inputs.get("budgets")
    ):
        if not orig_name.lower().endswith(".xlsx"):
            continue
        try:
            budget_rows.extend(budgets.parse_budget(payload, raw_path))
        except FinanceParseError as exc:
            record_parse_error("budgets", raw_path, exc)

    invoice_rows: list[dict[str, Any]] = []
    line_rows: list[dict[str, Any]] = []
    invoice_files = _read_source_files(spark, "isdoc", inputs.get("isdoc"))

    isdoc_stems: set[str] = set()
    for raw_path, orig_name, bdate, payload in invoice_files:
        if not orig_name.lower().endswith(".isdoc"):
            continue
        try:
            inv, inv_lines = isdoc.parse(payload, raw_path)
            effective_bdate = bdate or inv.get("issue_date")
            inv["business_date"] = effective_bdate
            for ln in inv_lines:
                ln["business_date"] = effective_bdate
            invoice_rows.append(inv)
            line_rows.extend(inv_lines)
            isdoc_stems.add(invoice_pdf.stem_key(orig_name))
        except FinanceParseError as exc:
            record_parse_error("isdoc", raw_path, exc)

    for raw_path, orig_name, bdate, _payload in invoice_files:
        if not orig_name.lower().endswith(".pdf"):
            continue
        if invoice_pdf.stem_key(orig_name) in isdoc_stems:
            continue
        try:
            pdf_inv = invoice_pdf.header(orig_name, raw_path)
            pdf_inv["business_date"] = bdate
            invoice_rows.append(pdf_inv)
        except FinanceParseError as exc:
            record_parse_error("isdoc", raw_path, exc)

    booked_rows: list[dict[str, Any]] = []
    for raw_path, orig_name, _bdate, payload in _read_source_files(
        spark, "accounting", inputs.get("accounting")
    ):
        if not orig_name.lower().endswith(".csv"):
            continue
        try:
            text = payload.decode("utf-8")
            booked_rows.extend(money_export.parse(text, raw_path))
        except (UnicodeDecodeError, FinanceParseError) as exc:
            record_parse_error("accounting", raw_path, exc)

    projects_df = spark.createDataFrame(project_rows, schema=PROJECTS_SCHEMA)
    suppliers_df = spark.createDataFrame(supplier_rows, schema=SUPPLIERS_SCHEMA)
    budget_lines_df = spark.createDataFrame(budget_rows, schema=BUDGET_LINES_SCHEMA)
    invoices_df = spark.createDataFrame(invoice_rows, schema=INVOICES_WORK_SCHEMA)
    lines_df = spark.createDataFrame(line_rows, schema=INVOICE_LINES_WORK_SCHEMA)
    booked_df = spark.createDataFrame(booked_rows, schema=BOOKED_COSTS_SCHEMA)

    invoices_df, lines_df, duplicate_issues = dq_checks.dedupe(invoices_df, lines_df)
    invoices_df, lines_df = project_codes.assign(
        invoices_df, lines_df, booked_df, projects_df, suppliers_df
    )
    check_issues = dq_checks.run(invoices_df, lines_df, booked_df, budget_lines_df)

    _write_clean_table(spark, "projects", projects_df)
    _write_clean_table(spark, "suppliers", suppliers_df)
    _write_clean_table(spark, "budget_lines", budget_lines_df)
    _write_clean_table(spark, "invoices", invoices_df)
    _write_clean_table(spark, "invoice_lines", lines_df)
    _write_clean_table(spark, "booked_costs", booked_df)

    all_issues = parse_issues + duplicate_issues + check_issues
    write_issues(spark, "finance", all_issues)
