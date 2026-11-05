"""Shared configuration: every path, database name, code list and service setting.

`docs/contracts.md` describes these values for people; this module is what the code imports. Read the values
through the module (`config.CLEAN_DB`), not `from common.config import CLEAN_DB`, so tests can redirect them.

One environment variable switches the whole pipeline to the 10x experiment dataset: `FVE_DATASET=x10`.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import NamedTuple

DATASETS = ("main", "x10")


def _dataset() -> str:
    value = os.environ.get("FVE_DATASET", "main")
    if value not in DATASETS:
        raise ValueError(f"FVE_DATASET must be one of {', '.join(DATASETS)}, got {value!r}")
    return value


DATASET = _dataset()
_X10 = DATASET == "x10"

# Local folders (inside the client container the repo is /repo).
REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / ("sources_x10" if _X10 else "sources")
OUT_DIR = REPO_ROOT / ("out_x10" if _X10 else "out")
LEDGER_DIR = OUT_DIR / "ledger"

# HDFS (paths without a scheme resolve against fs.defaultFS, hdfs://namenode:8020 in the stack).
LAKE_ROOT = "/bench/x10/lake" if _X10 else "/lake"
LAKE_RAW = f"{LAKE_ROOT}/raw"
LAKE_CLEAN = f"{LAKE_ROOT}/clean"
LAKE_DW = f"{LAKE_ROOT}/dw"

# Hive databases.
CLEAN_DB = "fve_clean_x10" if _X10 else "fve_clean"
DW_DB = "fve_dw_x10" if _X10 else "fve_dw"

# Synthetic data.
SEED = 312
DATA_START = date(2016, 1, 1)
DATA_END = date(2026, 10, 31)

# Projects.
PROJECT_CODE_RE = r"^FVE-\d{4}-\d{2}$"
PROJECT_CODE_PATTERN = re.compile(PROJECT_CODE_RE)
PROJECT_STATUSES = ("ACTIVE", "COMPLETED", "NOT_SIGNED")
UNASSIGNED = "UNASSIGNED"

# Cost categories: code -> (display name, group).
CATEGORY_GROUPS = ("technology", "construction", "services")
CATEGORIES: dict[str, tuple[str, str]] = {
    "PANELS": ("Panels", "technology"),
    "INVERTERS": ("Inverters", "technology"),
    "BATTERIES": ("Batteries", "technology"),
    "STRUCTURES": ("Mounting structures", "construction"),
    "CABLES": ("Cables", "construction"),
    "EARTHWORKS": ("Earthworks", "construction"),
    "GRID": ("Grid connection", "construction"),
    "DESIGN": ("Design", "services"),
    "SURVEY": ("Survey", "services"),
    "OTHER": ("Other", "services"),
}


class Bank(NamedTuple):
    """One of the company's banks and its (fake) account there."""

    name: str
    bank_code: str  # 4 digits
    account: str  # digits only, no leading zeros, no prefix
    format: str  # GPC or STA
    frequency: str  # daily or monthly


BANKS: dict[str, Bank] = {
    "RB": Bank("Raiffeisenbank", "5500", "2101234567", "GPC", "daily"),
    "UCB": Bank("UniCredit Bank", "2700", "1387654321", "GPC", "monthly"),
    "KB": Bank("Komerční banka", "0100", "1234567890", "GPC", "monthly"),
    "CS": Bank("Česká spořitelna", "0800", "2900112233", "STA", "monthly"),
}
CURRENCY = "CZK"


class RawSource(NamedTuple):
    """Where a source's files sit under SOURCES_DIR and how the collection job finds them."""

    folder: str  # relative to SOURCES_DIR, '/'-separated
    pattern: str  # glob relative to folder
    keep_project: bool  # raw path keeps the project folder (/lake/raw/<source>/<project>/<yyyy>/<mm>/...)


RAW_SOURCES: dict[str, RawSource] = {
    "master": RawSource("master", "*.csv", False),
    "budgets": RawSource("drive/budgets", "*.xlsx", False),
    "isdoc": RawSource("mailbox/invoices", "*.isdoc", False),
    "invoice_pdf": RawSource("mailbox/invoices", "*.pdf", False),
    "accounting": RawSource("drive/accounting", "*.csv", False),
    "bank_gpc": RawSource("mailbox/bank", "*/*.gpc", False),
    "bank_sta": RawSource("mailbox/bank", "*/*.sta", False),
    "bank_txt": RawSource("mailbox/bank", "*/*.txt", False),
    "kpc": RawSource("drive/payments", "*.kpc", False),
    "photos": RawSource("mailbox/photos", "*.jpg", False),
    "video": RawSource("drive/projects", "*/videos/*.mp4", True),
    "docs": RawSource("drive/projects", "*/*.*", True),
}

# Services in the Docker stack (host names are compose service names).
HIVE_HOST = "hiveserver2"
HIVE_PORT = 10000
SPARKSQL_PORT = 10001
HBASE_HOST = "hbase"
HBASE_PORT = 9090
HBASE_TABLE = "media_catalog"


def is_project_code(value: str) -> bool:
    """True if `value` is a project code `FVE-YYYY-NN`."""
    return PROJECT_CODE_PATTERN.fullmatch(value) is not None
