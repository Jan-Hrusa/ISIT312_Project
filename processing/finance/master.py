"""Parsers for master data CSVs (projects.csv and suppliers.csv)."""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from common import config

ICO_RE = re.compile(r"^\d{8}$")
BANK_CODE_RE = re.compile(r"^\d{4}$")


class FinanceParseError(ValueError):
    """Raised when a raw finance file cannot be parsed."""

    def __init__(self, message: str, source_file: str | None = None) -> None:
        super().__init__(message)
        self.source_file = source_file


def _req_str(row: dict[str, Any], key: str, source_file: str) -> str:
    val = (row.get(key) or "").strip()
    if not val:
        raise FinanceParseError(f"Missing required field {key!r}", source_file)
    return val


def _opt_date(val: str | None, field: str, source_file: str) -> date | None:
    if val is None or val.strip() == "":
        return None
    try:
        return date.fromisoformat(val.strip())
    except ValueError as exc:
        raise FinanceParseError(f"Invalid date {val!r} in {field}", source_file) from exc


def _req_decimal(val: str | None, field: str, source_file: str, scale: str = "0.01") -> Decimal:
    if val is None or val.strip() == "":
        raise FinanceParseError(f"Missing decimal in {field}", source_file)
    cleaned = val.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned).quantize(Decimal(scale))
    except InvalidOperation as exc:
        raise FinanceParseError(f"Invalid decimal {val!r} in {field}", source_file) from exc


def _req_bool(val: str | None, field: str, source_file: str) -> bool:
    if val is None or val.strip() == "":
        raise FinanceParseError(f"Missing boolean in {field}", source_file)
    low = val.strip().lower()
    if low == "true":
        return True
    if low == "false":
        return False
    raise FinanceParseError(f"Invalid boolean {val!r} in {field}", source_file)


def parse_projects(text: str, source_file: str) -> list[dict[str, Any]]:
    """Parse master/projects.csv into contract rows for fve_clean.projects."""
    if not text or not text.strip():
        raise FinanceParseError("Empty projects.csv", source_file)

    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=",")
    expected = [
        "project_code",
        "name",
        "town",
        "region",
        "lat",
        "lon",
        "radius_m",
        "mwp",
        "has_battery",
        "contract_value",
        "offer_date",
        "signed_date",
        "construction_start",
        "construction_end",
        "status",
    ]
    if reader.fieldnames != expected:
        raise FinanceParseError(f"Unexpected projects.csv columns: {reader.fieldnames}", source_file)

    rows: list[dict[str, Any]] = []
    for raw in reader:
        if None in raw or any(v is None for v in raw.values()):
            raise FinanceParseError("Malformed CSV row in projects.csv", source_file)

        project_code = _req_str(raw, "project_code", source_file)
        if not config.is_project_code(project_code):
            raise FinanceParseError(f"Invalid project_code {project_code!r}", source_file)

        status = _req_str(raw, "status", source_file).upper()
        if status not in config.PROJECT_STATUSES:
            raise FinanceParseError(f"Invalid project status {status!r}", source_file)

        try:
            lat = float(_req_str(raw, "lat", source_file))
            lon = float(_req_str(raw, "lon", source_file))
            radius_m = int(_req_str(raw, "radius_m", source_file))
        except ValueError as exc:
            raise FinanceParseError(f"Invalid numeric coordinate/radius: {exc}", source_file) from exc

        offer_date = _opt_date(raw.get("offer_date"), "offer_date", source_file)
        if offer_date is None:
            raise FinanceParseError("Missing offer_date in projects.csv", source_file)

        rows.append(
            {
                "project_code": project_code,
                "name": _req_str(raw, "name", source_file),
                "town": _req_str(raw, "town", source_file),
                "region": _req_str(raw, "region", source_file),
                "lat": lat,
                "lon": lon,
                "radius_m": radius_m,
                "mwp": _req_decimal(raw.get("mwp"), "mwp", source_file, "0.01"),
                "has_battery": _req_bool(raw.get("has_battery"), "has_battery", source_file),
                "contract_value": _req_decimal(
                    raw.get("contract_value"), "contract_value", source_file, "0.01"
                ),
                "offer_date": offer_date,
                "signed_date": _opt_date(raw.get("signed_date"), "signed_date", source_file),
                "construction_start": _opt_date(
                    raw.get("construction_start"), "construction_start", source_file
                ),
                "construction_end": _opt_date(raw.get("construction_end"), "construction_end", source_file),
                "status": status,
                "source_file": source_file,
            }
        )

    if not rows:
        raise FinanceParseError("No rows in projects.csv", source_file)
    return rows


def parse_suppliers(text: str, source_file: str) -> list[dict[str, Any]]:
    """Parse master/suppliers.csv into contract rows for fve_clean.suppliers."""
    if not text or not text.strip():
        raise FinanceParseError("Empty suppliers.csv", source_file)

    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=",")
    expected = ["ico", "name", "category", "bank_account", "bank_code"]
    if reader.fieldnames != expected:
        raise FinanceParseError(f"Unexpected suppliers.csv columns: {reader.fieldnames}", source_file)

    rows: list[dict[str, Any]] = []
    for raw in reader:
        if None in raw or any(v is None for v in raw.values()):
            raise FinanceParseError("Malformed CSV row in suppliers.csv", source_file)

        ico = _req_str(raw, "ico", source_file)
        if not ICO_RE.fullmatch(ico):
            raise FinanceParseError(f"Invalid supplier IČO {ico!r}", source_file)

        category = _req_str(raw, "category", source_file).upper()
        if category not in config.CATEGORIES:
            raise FinanceParseError(f"Unknown category {category!r}", source_file)

        bank_account = _req_str(raw, "bank_account", source_file).lstrip("0")
        if not bank_account or not bank_account.isdigit():
            raise FinanceParseError(f"Invalid bank_account {bank_account!r}", source_file)

        bank_code = _req_str(raw, "bank_code", source_file)
        if not BANK_CODE_RE.fullmatch(bank_code):
            raise FinanceParseError(f"Invalid bank_code {bank_code!r}", source_file)

        rows.append(
            {
                "ico": ico,
                "name": _req_str(raw, "name", source_file),
                "category": category,
                "bank_account": bank_account,
                "bank_code": bank_code,
                "source_file": source_file,
            }
        )

    if not rows:
        raise FinanceParseError("No rows in suppliers.csv", source_file)
    return rows
