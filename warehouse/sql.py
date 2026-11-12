
"""Shared SQL utilities for the Hive data warehouse."""

from __future__ import annotations

import re
from pathlib import Path

from common import config


_VARIABLE = re.compile(r"\$\{([^}]+)\}")
_NAME = re.compile(r"^\s*--\s*name:\s*(\S+)\s*$", re.IGNORECASE)


def _parameters(params: dict) -> dict[str, str]:
    """Combine configuration defaults with caller overrides."""
    values = {
        "DW_DB": config.DW_DB,
        "CLEAN_DB": config.CLEAN_DB,
        "LAKE_DW": config.LAKE_DW,
        "LAKE_CLEAN": config.LAKE_CLEAN,
    }
    values.update(params)
    return {key: str(value) for key, value in values.items()}


def _substitute(sql: str, values: dict[str, str]) -> str:
    """Replace variables and reject unknown placeholders."""

    def replace(match):
        name = match.group(1)
        if name not in values:
            raise ValueError(f"Unknown SQL variable: {name}")
        return values[name]

    return _VARIABLE.sub(replace, sql)


def _statements(sql: str) -> list[str]:
    """Split SQL on semicolons at the end of a line."""
    statements = []
    current = []

    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue

        current.append(line)

        if line.rstrip().endswith(";"):
            statement = "\n".join(current).strip()
            statement = statement[:-1].strip()

            if statement:
                statements.append(statement)

            current = []

    trailing = "\n".join(current).strip()
    if trailing:
        statements.append(trailing)

    return statements


def render(path: str | Path, **params) -> list[str]:
    """Render a SQL file into executable statements."""
    sql = Path(path).read_text(encoding="utf-8")
    sql = _substitute(sql, _parameters(params))
    return _statements(sql)


def named_queries(path: str | Path, **params) -> dict[str, str]:
    """Read SQL blocks introduced by '-- name: query_name'."""
    sql = Path(path).read_text(encoding="utf-8")
    sql = _substitute(sql, _parameters(params))

    queries = {}
    name = None
    lines = []

    def save_query():
        if name is None:
            return

        statements = _statements("\n".join(lines))
        if len(statements) != 1:
            raise ValueError(
                f"Named query {name!r} must contain exactly one statement"
            )
        if name in queries:
            raise ValueError(f"Duplicate named query: {name}")
        queries[name] = statements[0]

    for line in sql.splitlines():
        match = _NAME.match(line)

        if match:
            save_query()
            name = match.group(1)
            lines = []
        elif name is not None:
            lines.append(line)

    save_query()
    return queries


def run_file(spark, path: str | Path):
    """Execute each rendered statement using Spark SQL."""
    return [spark.sql(statement) for statement in render(path)]
