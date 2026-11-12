"""Spark job for finance processing."""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from pyspark import RDD, StorageLevel
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

# Files per Spark partition when reading (one binaryFiles call per chunk, see _parse_all).
FILES_PER_PARTITION = 200

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

# Kinds of the tagged records the per-file parser emits besides table rows (first element of each record).
_ISSUE = "issue"
_PDF_ISSUE = "pdf_issue"
_ISDOC_INVOICE = "isdoc_invoice"
_PDF_INVOICE = "pdf_invoice"


def _spark_schema(table: str, extra_cols: list[tuple[str, Any]] | None = None) -> StructType:
    fields = [
        StructField(name, _HIVE_TO_SPARK[hive_type], True) for name, hive_type in schemas.CLEAN_TABLES[table]
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


def _local_mtime_date(uri_or_path: str) -> date | None:
    """business_date from the file mtime (UTC) in inputs=... mode.

    None when the file can't be stat'ed; Spark then fails the run on the same file (a listed file that is
    missing is an error of the input list, not a PARSE_ERROR).
    """
    try:
        if uri_or_path.startswith("file:"):
            p = Path(unquote(urlparse(uri_or_path).path))
        else:
            p = Path(uri_or_path)
        ts = p.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).date()
    except OSError:
        return None


def _collect_source_files(
    spark: SparkSession, inputs: dict[str, list[str]] | None
) -> dict[str, list[tuple[str, str, date | None]]]:
    """Return {source: [(read_path, raw_path_for_table, business_date), ...]}."""
    result: dict[str, list[tuple[str, str, date | None]]] = {s: [] for s in FINANCE_SOURCES}
    if inputs is not None:
        for source in FINANCE_SOURCES:
            for p in inputs.get(source, []):
                result[source].append((p, _strip_hdfs_scheme(p), _local_mtime_date(p)))
        return result

    for source in FINANCE_SOURCES:
        df = lake.current_raw_files(spark, source)
        for row in df.collect():
            raw_p = _strip_hdfs_scheme(row.raw_path)
            result[source].append((raw_p, raw_p, row.business_date))
    return result


def _parse_file(source: str, raw_p: str, bdate: date | None, data: bytes) -> list[tuple]:
    """Parse one raw finance file into tagged records (runs on the executors).

    Records: (<table>, row) for projects, suppliers, budget_lines, invoice_lines and booked_costs;
    (_ISDOC_INVOICE, stem, row) and (_PDF_INVOICE, stem, row) for invoices; (_ISSUE, issue) and
    (_PDF_ISSUE, stem, issue), issue = (issue_type, source, record_ref, project_code, detail).
    """
    fname = PurePosixPath(raw_p.replace("\\", "/")).name
    try:
        if source == "master":
            text = data.decode("utf-8")
            if fname.lower().startswith("projects"):
                return [("projects", r) for r in master.parse_projects(text, raw_p)]
            if fname.lower().startswith("suppliers"):
                return [("suppliers", r) for r in master.parse_suppliers(text, raw_p)]
            raise FinanceParseError(f"Unknown master file {fname!r}", raw_p)
        if source == "budgets":
            return [("budget_lines", r) for r in budgets.parse_budget(data, raw_p)]
        if source == "isdoc":
            inv, lines = isdoc.parse(data, raw_p)
            inv["business_date"] = bdate
            line_records = [("invoice_lines", {**ln, "business_date": bdate}) for ln in lines]
            return [(_ISDOC_INVOICE, invoice_pdf.stem_key(raw_p), inv), *line_records]
        if source == "invoice_pdf":
            stem = invoice_pdf.stem_key(raw_p)
            try:
                if not data.startswith(b"%PDF"):
                    raise FinanceParseError("Invalid PDF magic header", raw_p)
                inv = invoice_pdf.header(fname, raw_p)
            except FinanceParseError as exc:
                # An error only when no ISDOC of the same name was parsed; run() decides that.
                return [(_PDF_ISSUE, stem, ("PARSE_ERROR", source, raw_p, None, str(exc)))]
            inv["business_date"] = bdate
            return [(_PDF_INVOICE, stem, inv)]
        if source == "accounting":
            return [("booked_costs", r) for r in money_export.parse(data.decode("utf-8"), raw_p)]
        raise FinanceParseError(f"Unknown finance source {source!r}", raw_p)
    except (UnicodeDecodeError, FinanceParseError) as exc:
        return [(_ISSUE, ("PARSE_ERROR", source, raw_p, None, str(exc)))]


def _parse_all(spark: SparkSession, entries: list[tuple[str, str, str, date | None]]) -> RDD:
    """Read the listed files with binaryFiles and parse them on the executors; file bytes never reach the
    driver. `entries` = (source, read_path, raw_path, business_date). Returns the persisted record RDD."""
    sc = spark.sparkContext
    if not entries:
        return sc.emptyRDD()
    wanted = {_norm_lookup_key(read_p): (source, raw_p, bdate) for source, read_p, raw_p, bdate in entries}
    wanted_b = sc.broadcast(wanted)
    # binaryFiles packs small files into splits of up to spark.files.maxPartitionBytes (128 MB) and ignores
    # minPartitions below that, so the whole dataset would be read by one task; one call per chunk of files
    # gives one partition each.
    chunks = [entries[i : i + FILES_PER_PARTITION] for i in range(0, len(entries), FILES_PER_PARTITION)]
    files = sc.union([sc.binaryFiles(",".join(e[1] for e in chunk)) for chunk in chunks])

    def parse_pair(kv):
        source, raw_p, bdate = wanted_b.value[_norm_lookup_key(kv[0])]
        return _parse_file(source, raw_p, bdate, bytes(kv[1]))

    return files.flatMap(parse_pair).persist(StorageLevel.MEMORY_AND_DISK)


def _rows_df(spark: SparkSession, records: RDD, kind: str, schema: StructType, pos: int = 1) -> DataFrame:
    """DataFrame of the dict rows at position `pos` of one kind of record, in the schema's column order."""
    names = schema.fieldNames()
    rows = records.filter(lambda r: r[0] == kind).map(lambda r: tuple(r[pos].get(n) for n in names))
    return spark.createDataFrame(rows, schema)


def run(spark: SparkSession, inputs: dict[str, list[str]] | None = None) -> dict[str, int]:
    """Run the finance processing pipeline step and return table/issue row counts."""
    source_map = _collect_source_files(spark, inputs)
    entries = [(s, read_p, raw_p, bdate) for s in FINANCE_SOURCES for read_p, raw_p, bdate in source_map[s]]
    records = _parse_all(spark, entries)

    # Only small results go to the driver: the parse issues and the stems of the parsed ISDOCs.
    small = records.filter(lambda r: r[0] in (_ISSUE, _PDF_ISSUE, _ISDOC_INVOICE)).map(
        lambda r: (r[0], r[1], r[2] if r[0] == _PDF_ISSUE else None)
    )
    isdoc_stems: set[str] = set()
    parse_issues: list[tuple] = []
    pdf_issues: list[tuple[str, tuple]] = []
    for kind, first, second in small.collect():
        if kind == _ISSUE:
            parse_issues.append(first)
        elif kind == _PDF_ISSUE:
            pdf_issues.append((first, second))
        else:
            isdoc_stems.add(first)
    parse_issues.extend(issue for stem, issue in pdf_issues if stem not in isdoc_stems)

    # PDF-only rows only for invoices without a successfully parsed ISDOC of the same name.
    stems_b = spark.sparkContext.broadcast(isdoc_stems)
    pdf_only = records.filter(lambda r: r[0] == _PDF_INVOICE and r[1] not in stems_b.value)
    invoice_schema = _spark_schema("invoices", [("business_date", DateType())])
    invoices_df = _rows_df(spark, records, _ISDOC_INVOICE, invoice_schema, pos=2).unionByName(
        _rows_df(spark, pdf_only, _PDF_INVOICE, invoice_schema, pos=2)
    )
    lines_df = _rows_df(
        spark,
        records,
        "invoice_lines",
        _spark_schema("invoice_lines", [("source_file", StringType()), ("business_date", DateType())]),
    )
    projects_df = _rows_df(spark, records, "projects", _spark_schema("projects"))
    suppliers_df = _rows_df(spark, records, "suppliers", _spark_schema("suppliers"))
    budgets_df = _rows_df(spark, records, "budget_lines", _spark_schema("budget_lines"))
    booked_df = _rows_df(spark, records, "booked_costs", _spark_schema("booked_costs"))

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
        records.unpersist()
