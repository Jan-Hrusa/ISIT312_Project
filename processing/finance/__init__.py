"""Spark job for finance processing."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DecimalType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from common import dq, lake, schemas, tables
from processing.finance import budgets, invoice_pdf, isdoc, master, money_export
from processing.finance.master import FinanceParseError

__all__ = ["FinanceParseError", "run"]

FINANCE_SOURCES = ("master", "budgets", "isdoc", "invoice_pdf", "accounting")

_HDFS_PREFIX_RE = re.compile(r"^hdfs://[^/]+")

_HIVE_TO_SPARK = {
    "STRING": StringType(),
    "INT": IntegerType(),
    "DOUBLE": DoubleType(),
    "BOOLEAN": BooleanType(),
    "DATE": DateType(),
    "DECIMAL(14,2)": DecimalType(14, 2),
    "DECIMAL(12,3)": DecimalType(12, 3),
    "DECIMAL(5,2)": DecimalType(5, 2),
    "DECIMAL(4,2)": DecimalType(4, 2),
}


def _spark_schema(
    table: str, extra_cols: list[tuple[str, Any]] | None = None
) -> StructType:
    fields = [
        StructField(name, _HIVE_TO_SPARK[hive_type], True)
        for name, hive_type in schemas.CLEAN_TABLES[table]
    ]
    if extra_cols:
        fields.extend(StructField(n, t, True) for n, t in extra_cols)
    return StructType(fields)


def _strip_hdfs_scheme(path: str) -> str:
    return _HDFS_PREFIX_RE.sub("", path)


def _norm_lookup_key(uri_or_path: str) -> str:
    """Canonical path key so Spark binaryFiles keys match input paths reliably."""
    s = _strip_hdfs_scheme(uri_or_path)
    if s.startswith("file:"):
        parsed = urlparse(s)
        return os.path.normpath(unquote(parsed.path))
    return s


def _local_mtime_date(uri_or_path: str) -> date:
    """Fallback business_date from file mtime in UTC when running in inputs=... mode."""
    try:
        if uri_or_path.startswith("file:"):
            p = Path(unquote(urlparse(uri_or_path).path))
        else:
            p = Path(uri_or_path)
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    except OSError:
        return date(2026, 1, 1)


def _collect_source_files(
    spark: SparkSession, inputs: dict[str, list[str]] | None
) -> dict[str, list[tuple[str, str, date]]]:
    """Return {source: [(read_path, raw_path_for_table, business_date), ...]}."""
    result: dict[str, list[tuple[str, str, date]]] = {s: [] for s in FINANCE_SOURCES}
    if inputs is not None:
        for source in FINANCE_SOURCES:
            for p in inputs.get(source, []):
                clean_raw = _strip_hdfs_scheme(p)
                bdate = _local_mtime_date(p)
                result[source].append((p, clean_raw, bdate))
        return result

    for source in FINANCE_SOURCES:
        df = lake.current_raw_files(spark, source)
        for row in df.collect():
            raw_p = _strip_hdfs_scheme(row.raw_path)
            result[source].append((raw_p, raw_p, row.business_date))
    return result


def _read_bytes_map(
    spark: SparkSession, file_entries: list[tuple[str, str, date]]
) -> dict[str, bytes]:
    """Read all files via SparkContext.binaryFiles and map back to canonical raw_path."""
    if not file_entries:
        return {}
    sc = spark.sparkContext
    lookup = {_norm_lookup_key(read_p): raw_p for read_p, raw_p, _ in file_entries}
    read_paths = [read_p for read_p, _, _ in file_entries]
    rdd = sc.binaryFiles(",".join(read_paths))
    out: dict[str, bytes] = {}
    for k, content in rdd.collect():
        norm_k = _norm_lookup_key(k)
        raw_p = lookup.get(norm_k, _strip_hdfs_scheme(k))
        out[raw_p] = bytes(content)
    return out


def run(
    spark: SparkSession, inputs: dict[str, list[str]] | None = None
) -> dict[str, int]:
    """Run the finance processing pipeline step and return table/issue row counts."""
    source_map = _collect_source_files(spark, inputs)
    all_entries = [entry for entries in source_map.values() for entry in entries]
    bytes_by_raw_path = _read_bytes_map(spark, all_entries)

    project_rows: list[dict[str, Any]] = []
    supplier_rows: list[dict[str, Any]] = []
    budget_rows: list[dict[str, Any]] = []
    invoice_rows: list[dict[str, Any]] = []
    line_rows: list[dict[str, Any]] = []
    booked_rows: list[dict[str, Any]] = []
    parse_issues: list[tuple[str, str, str, str | None, str]] = []

    parsed_isdoc_stems: set[str] = set()

    for _, raw_p, _ in sorted(source_map["master"], key=lambda x: x[1]):
        raw_bytes = bytes_by_raw_path.get(raw_p, b"")
        fname = PurePosixPath(raw_p.replace("\\", "/")).name.lower()
        try:
            text = raw_bytes.decode("utf-8")
            if fname.startswith("projects"):
                project_rows.extend(master.parse_projects(text, raw_p))
            elif fname.startswith("suppliers"):
                supplier_rows.extend(master.parse_suppliers(text, raw_p))
            else:
                raise FinanceParseError(f"Unknown master file {fname!r}", raw_p)
        except (UnicodeDecodeError, FinanceParseError) as exc:
            parse_issues.append(("PARSE_ERROR", "master", raw_p, None, str(exc)))

    # 2. Budgets (.xlsx)
    for _, raw_p, _ in sorted(source_map["budgets"], key=lambda x: x[1]):
        raw_bytes = bytes_by_raw_path.get(raw_p, b"")
        try:
            budget_rows.extend(budgets.parse_budget(raw_bytes, raw_p))
        except FinanceParseError as exc:
            parse_issues.append(("PARSE_ERROR", "budgets", raw_p, None, str(exc)))

    # 3. ISDOC XML invoices (.isdoc)
    for _, raw_p, bdate in sorted(source_map["isdoc"], key=lambda x: x[1]):
        raw_bytes = bytes_by_raw_path.get(raw_p, b"")
        try:
            inv, lines = isdoc.parse(raw_bytes, raw_p)
            inv["business_date"] = bdate
            for ln in lines:
                ln["business_date"] = bdate
            invoice_rows.append(inv)
            line_rows.extend(lines)
            parsed_isdoc_stems.add(invoice_pdf.stem_key(raw_p))
        except FinanceParseError as exc:
            parse_issues.append(("PARSE_ERROR", "isdoc", raw_p, None, str(exc)))

    # 4. PDF-only invoices (.pdf without a successfully parsed ISDOC of the same stem)
    for _, raw_p, bdate in sorted(source_map["invoice_pdf"], key=lambda x: x[1]):
        stem = invoice_pdf.stem_key(raw_p)
        if stem in parsed_isdoc_stems:
            continue
        raw_bytes = bytes_by_raw_path.get(raw_p, b"")
        try:
            if not raw_bytes.startswith(b"%PDF"):
                raise FinanceParseError("Invalid PDF magic header", raw_p)
            fname = PurePosixPath(raw_p.replace("\\", "/")).name
            inv = invoice_pdf.header(fname, raw_p)
            inv["business_date"] = bdate
            invoice_rows.append(inv)
        except FinanceParseError as exc:
            parse_issues.append(("PARSE_ERROR", "invoice_pdf", raw_p, None, str(exc)))

   
    for _, raw_p, _ in sorted(source_map["accounting"], key=lambda x: x[1]):
        raw_bytes = bytes_by_raw_path.get(raw_p, b"")
        try:
            text = raw_bytes.decode("utf-8")
            booked_rows.extend(money_export.parse(text, raw_p))
        except (UnicodeDecodeError, FinanceParseError) as exc:
            parse_issues.append(("PARSE_ERROR", "accounting", raw_p, None, str(exc)))


    projects_df = spark.createDataFrame(project_rows, _spark_schema("projects"))
    suppliers_df = spark.createDataFrame(supplier_rows, _spark_schema("suppliers"))
    budgets_df = spark.createDataFrame(budget_rows, _spark_schema("budget_lines"))
    booked_df = spark.createDataFrame(booked_rows, _spark_schema("booked_costs"))

    invoices_df = spark.createDataFrame(
        invoice_rows,
        _spark_schema("invoices", [("business_date", DateType())]),
    )
    lines_df = spark.createDataFrame(
        line_rows,
        _spark_schema(
            "invoice_lines",
            [("source_file", StringType()), ("business_date", DateType())],
        ),
    )

    all_issues_df: DataFrame = dq.issue_rows(spark, parse_issues)

    
    try:
        from processing.finance import dq_checks
    except ImportError:
        dq_checks = None  # type: ignore[assignment]

    try:
        from processing.finance import project_codes
    except ImportError:
        project_codes = None  # type: ignore[assignment]

    if dq_checks is not None and hasattr(dq_checks, "dedupe"):
        invoices_df, lines_df, dup_issues_df = dq_checks.dedupe(invoices_df, lines_df)
        all_issues_df = all_issues_df.unionByName(dup_issues_df)

    if project_codes is not None and hasattr(project_codes, "assign"):
        invoices_df, lines_df = project_codes.assign(
            invoices_df, lines_df, booked_df, projects_df, suppliers_df
        )

    if dq_checks is not None and hasattr(dq_checks, "run"):
        check_issues_df = dq_checks.run(invoices_df, lines_df, booked_df, budgets_df)
        all_issues_df = all_issues_df.unionByName(check_issues_df)


    projects_df = projects_df.cache()
    suppliers_df = suppliers_df.cache()
    budgets_df = budgets_df.cache()
    invoices_df = invoices_df.cache()
    lines_df = lines_df.cache()
    booked_df = booked_df.cache()

    try:
        tables.write_table(spark, projects_df, "projects")
        tables.write_table(spark, suppliers_df, "suppliers")
        tables.write_table(spark, budgets_df, "budget_lines")
        tables.write_table(spark, invoices_df, "invoices")
        tables.write_table(spark, lines_df, "invoice_lines")
        tables.write_table(spark, booked_df, "booked_costs")
        issues_count = dq.write_issues(spark, all_issues_df, job="finance")

        return {
            "projects": projects_df.count(),
            "suppliers": suppliers_df.count(),
            "budget_lines": budgets_df.count(),
            "invoices": invoices_df.count(),
            "invoice_lines": lines_df.count(),
            "booked_costs": booked_df.count(),
            "dq_issues": issues_count,
        }
    finally:
        for cached_df in (
            projects_df,
            suppliers_df,
            budgets_df,
            invoices_df,
            lines_df,
            booked_df,
        ):
            cached_df.unpersist()
