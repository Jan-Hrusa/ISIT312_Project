"""Small helpers shared by the finance generator modules."""

import os
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from common import config

CENT = Decimal("0.01")


def as_date(value) -> date:
    """Accept a date, datetime or ISO string (config may use any of them)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def category_codes() -> list[str]:
    """The ten cost-category codes, in config order."""
    codes = []
    for item in config.CATEGORIES:
        if isinstance(item, str):
            codes.append(item)
        elif isinstance(item, (tuple, list)):
            codes.append(item[0])
        elif isinstance(item, dict):
            codes.append(item.get("code") or item.get("category_code"))
        else:
            codes.append(item.code)
    return codes


DATA_START = as_date(config.DATA_START)
DATA_END = as_date(config.DATA_END)
CATEGORIES = category_codes()


def sources_dir() -> Path:
    return Path(config.SOURCES_DIR)


def ledger_dir() -> Path:
    return Path(config.LEDGER_DIR)


def q2(value) -> Decimal:
    """Round to 2 decimals, half up."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def business_ts(d: date) -> float:
    return datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc).timestamp()


def set_business_mtime(path, d: date) -> None:
    """Contract rule: every file's mtime = 12:00 UTC of its business date."""
    ts = business_ts(d)
    os.utime(path, (ts, ts))


def money(value) -> str:
    """Decimal with a point, 2 decimals, no thousands separator."""
    return f"{q2(value):.2f}"


def money_cz(value) -> str:
    """Decimal comma, 2 decimals, no thousands separator."""
    return money(value).replace(".", ",")
