"""Header row generator for PDF only invoices."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from common import config
from processing.finance.master import FinanceParseError

PDF_NAME_RE = re.compile(r"^(\d{8})_([A-Za-z0-9-]+)$")


def stem_key(file_name_or_path: str) -> str:
    """Extract canonical '<ico>_<number>' stem, stripping any '__<ingest_ts>' suffix."""
    name = PurePosixPath(file_name_or_path.replace("\\", "/")).name
    stem = PurePosixPath(name).stem
    if "__" in stem:
        stem = stem.split("__", 1)[0]
    return stem


def header(original_name: str, source_file: str) -> dict[str, Any]:
    """Create a skeleton invoice row from a PDF file name (<ico>_<number>.pdf)."""
    name = PurePosixPath(original_name.replace("\\", "/")).name
    if not name.lower().endswith(".pdf"):
        raise FinanceParseError(f"Expected .pdf file name, got {original_name!r}", source_file)

    base = stem_key(name)
    match = PDF_NAME_RE.fullmatch(base)
    if not match:
        raise FinanceParseError(f"Invalid invoice PDF file name {original_name!r}", source_file)

    supplier_ico, number = match.group(1), match.group(2)
    return {
        "invoice_id": f"{supplier_ico}-{number}",
        "supplier_ico": supplier_ico,
        "number": number,
        "vs": None,
        "issue_date": None,
        "due_date": None,
        "total_net": None,
        "total_vat": None,
        "total_gross": None,
        "currency": config.CURRENCY,
        "category": None,
        "project_code": None,
        "project_rule": None,
        "has_isdoc": False,
        "source_file": source_file,
    }
