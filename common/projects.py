"""Projects from the master file `sources/master/projects.csv`, for generators and pure-Python code.

Spark jobs read `fve_clean.projects` instead (common.tables.read_table).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import config
from common.schemas import SOURCE_COLUMNS

PROJECTS_CSV_COLUMNS = SOURCE_COLUMNS["master/projects.csv"]


@dataclass(frozen=True)
class Project:
    """One row of `projects` (columns as in common/schemas.py)."""

    project_code: str
    name: str
    town: str
    region: str
    lat: float
    lon: float
    radius_m: int
    mwp: Decimal
    has_battery: bool
    contract_value: Decimal
    offer_date: date
    signed_date: date | None
    construction_start: date | None
    construction_end: date | None
    status: str
    source_file: str | None = None

    @property
    def is_signed(self) -> bool:
        return self.status != "NOT_SIGNED"


def load_projects(path: str | Path | None = None) -> list[Project]:
    """Read projects.csv (UTF-8, comma, header row; dates yyyy-MM-dd; booleans true/false).

    path: default `<SOURCES_DIR>/master/projects.csv`. Raises ValueError naming the line for a bad row.
    """
    path = Path(path) if path is not None else config.SOURCES_DIR / "master" / "projects.csv"
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in PROJECTS_CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns: {', '.join(missing)}")
        projects = []
        for line_no, row in enumerate(reader, start=2):
            try:
                projects.append(_project(row))
            except ValueError as e:
                raise ValueError(f"{path}, line {line_no}: {e}") from e
    return projects


def active_on(projects: list[Project], day: date) -> list[Project]:
    """Signed projects whose construction period (start and end included) contains `day`."""
    return [
        p
        for p in projects
        if p.is_signed
        and p.construction_start is not None
        and p.construction_end is not None
        and p.construction_start <= day <= p.construction_end
    ]


def _project(row: dict[str, str]) -> Project:
    if None in row or None in row.values():
        raise ValueError("wrong number of fields")
    code = row["project_code"].strip()
    if not config.is_project_code(code):
        raise ValueError(f"bad project_code {code!r}")
    status = row["status"].strip()
    if status not in config.PROJECT_STATUSES:
        raise ValueError(f"bad status {status!r}")
    return Project(
        project_code=code,
        name=row["name"].strip(),
        town=row["town"].strip(),
        region=row["region"].strip(),
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        radius_m=int(row["radius_m"]),
        mwp=_decimal(row["mwp"], "mwp"),
        has_battery=_bool(row["has_battery"]),
        contract_value=_decimal(row["contract_value"], "contract_value"),
        offer_date=date.fromisoformat(row["offer_date"].strip()),
        signed_date=_optional_date(row["signed_date"]),
        construction_start=_optional_date(row["construction_start"]),
        construction_end=_optional_date(row["construction_end"]),
        status=status,
        source_file=row.get("source_file") or None,
    )


def _decimal(value: str, column: str) -> Decimal:
    try:
        return Decimal(value.strip())
    except InvalidOperation as e:
        raise ValueError(f"bad {column} {value!r}") from e


def _bool(value: str) -> bool:
    text = value.strip().lower()
    if text not in ("true", "false"):
        raise ValueError(f"bad has_battery {value!r} (true or false)")
    return text == "true"


def _optional_date(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None
