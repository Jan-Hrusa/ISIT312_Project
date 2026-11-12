"""Parser for project budget XLSX workbook."""

from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl

from common import config
from processing.finance.master import FinanceParseError


def _parse_amount(val: Any, source_file: str) -> Decimal:
    if val is None or isinstance(val, bool):
        raise FinanceParseError("Missing budget amount", source_file)
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val)).quantize(Decimal("0.01"))
    cleaned = str(val).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise FinanceParseError(f"Invalid budget amount {val!r}", source_file) from exc


def parse_budget(xlsx_bytes: bytes, source_file: str) -> list[dict[str, Any]]:
    """Parse sheet 'Budget' from an XLSX workbook into fve_clean.budget_lines rows."""
    if not xlsx_bytes:
        raise FinanceParseError("Empty XLSX file", source_file)

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True, read_only=True)
    except Exception as exc:
        raise FinanceParseError(f"Cannot open XLSX workbook: {exc}", source_file) from exc

    if "Budget" not in wb.sheetnames:
        raise FinanceParseError("Missing 'Budget' sheet in workbook", source_file)

    ws = wb["Budget"]
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration as exc:
        raise FinanceParseError("Empty 'Budget' sheet", source_file) from exc

    header_names = [str(c).strip() if c is not None else "" for c in header[:3]]
    if header_names != ["project_code", "category", "amount_czk"]:
        raise FinanceParseError(f"Unexpected budget header {header_names}", source_file)

    rows: list[dict[str, Any]] = []
    seen_categories: set[str] = set()
    project_codes: set[str] = set()

    for raw in rows_iter:
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        project_code = str(raw[0] or "").strip()
        category = str(raw[1] or "").strip()
        amount = _parse_amount(raw[2] if len(raw) > 2 else None, source_file)

        if not config.is_project_code(project_code):
            raise FinanceParseError(f"Invalid project_code {project_code!r}", source_file)
        if category not in config.CATEGORIES:
            raise FinanceParseError(f"Unknown budget category {category!r}", source_file)
        if category in seen_categories:
            raise FinanceParseError(f"Duplicate budget category {category!r}", source_file)

        seen_categories.add(category)
        project_codes.add(project_code)
        rows.append(
            {
                "project_code": project_code,
                "category": category,
                "amount": amount,
                "source_file": source_file,
            }
        )

    if len(project_codes) != 1:
        raise FinanceParseError(
            f"Budget workbook must contain exactly 1 project_code, got {project_codes}",
            source_file,
        )
    if set(seen_categories) != set(config.CATEGORIES):
        raise FinanceParseError(
            f"Budget workbook must have all 10 categories, got {sorted(seen_categories)}",
            source_file,
        )

    return rows
