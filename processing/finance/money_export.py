"""Parser for weekly Money S3 accounting exports."""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath
from typing import Any

from common import config
from processing.finance.master import FinanceParseError

WEEK_RE = re.compile(r"money_export_(\d{4}-W\d{2})")
ICO_RE = re.compile(r"^\d{8}$")


def parse_decimal_comma(val: str | None, source_file: str = "") -> Decimal:
    """Parse a Czech decimal string ('1234,50' or '1 234,50') into DECIMAL(14,2)."""
    if val is None or val.strip() == "":
        raise FinanceParseError("Empty decimal value", source_file)
    cleaned = val.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise FinanceParseError(f"Invalid decimal value {val!r}", source_file) from exc


def _parse_date(val: str | None, field: str, source_file: str) -> date:
    if val is None or val.strip() == "":
        raise FinanceParseError(f"Missing date in {field}", source_file)
    try:
        return date.fromisoformat(val.strip())
    except ValueError as exc:
        raise FinanceParseError(f"Invalid date {val!r} in {field}", source_file) from exc


def _extract_export_week(source_file: str) -> str:
    name = PurePosixPath(source_file.replace("\\", "/")).name
    match = WEEK_RE.search(name)
    if not match:
        raise FinanceParseError(f"Cannot extract export_week from file name {source_file!r}", source_file)
    return match.group(1)


def _normalize_vs(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip().lstrip("0")
    return stripped if stripped != "" else None


def parse(text: str, source_file: str) -> list[dict[str, Any]]:
    """Parse a ';' separated Money S3 CSV export into fve_clean.booked_costs rows."""
    if not text or not text.strip():
        raise FinanceParseError("Empty Money S3 export file", source_file)

    export_week = _extract_export_week(source_file)
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";")
    expected = [
        "doc_ref",
        "supplier_ico",
        "vs",
        "issue_date",
        "due_date",
        "booking_date",
        "project_code",
        "cost_centre",
        "category",
        "amount_net_czk",
        "amount_gross_czk",
    ]
    if reader.fieldnames != expected:
        raise FinanceParseError(f"Unexpected Money S3 header: {reader.fieldnames}", source_file)

    rows: list[dict[str, Any]] = []
    for raw in reader:
        if None in raw or any(v is None for v in raw.values()):
            raise FinanceParseError("Malformed row in Money S3 export", source_file)

        doc_ref = raw["doc_ref"].strip()
        if not doc_ref:
            raise FinanceParseError("Missing doc_ref in Money S3 export", source_file)

        supplier_ico = raw["supplier_ico"].strip()
        if not ICO_RE.fullmatch(supplier_ico):
            raise FinanceParseError(f"Invalid supplier_ico {supplier_ico!r}", source_file)

        project_code_raw = raw["project_code"].strip()
        project_code: str | None = project_code_raw if project_code_raw else None
        if project_code is not None and not config.is_project_code(project_code):
            raise FinanceParseError(f"Invalid project_code {project_code!r}", source_file)

        category = raw["category"].strip()
        if category not in config.CATEGORIES:
            raise FinanceParseError(f"Unknown category {category!r}", source_file)

        cost_centre = raw["cost_centre"].strip()
        if not cost_centre:
            raise FinanceParseError("Missing cost_centre in Money S3 export", source_file)

        rows.append(
            {
                "doc_ref": doc_ref,
                "supplier_ico": supplier_ico,
                "vs": _normalize_vs(raw.get("vs")),
                "issue_date": _parse_date(raw.get("issue_date"), "issue_date", source_file),
                "due_date": _parse_date(raw.get("due_date"), "due_date", source_file),
                "booking_date": _parse_date(raw.get("booking_date"), "booking_date", source_file),
                "project_code": project_code,
                "cost_centre": cost_centre,
                "category": category,
                "amount": parse_decimal_comma(raw.get("amount_net_czk"), source_file),
                "amount_gross": parse_decimal_comma(raw.get("amount_gross_czk"), source_file),
                "export_week": export_week,
                "source_file": source_file,
            }
        )

    return rows
