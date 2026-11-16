"""Bank statement and payment order parsing."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from common import config

if TYPE_CHECKING:
    from pyspark.sql import SparkSession


class BankParseError(ValueError):
    """A malformed bank file."""


def _digits(value: str, field: str) -> str:
    if not value.isascii() or not value.isdecimal():
        raise BankParseError(f"invalid {field}: {value!r}")
    return value


def _symbol(value: str) -> str | None:
    if not value:
        return None
    return _digits(value, "symbol").lstrip("0") or None


def _account(value: str) -> str:
    return _digits(value, "account").lstrip("0") or "0"


def _date(value: str, fmt: str):
    if len(value) == 6:
        _digits(value, "date")
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise BankParseError(f"invalid date: {value!r}")


def _bank(account: str, *, statement_format: str = "", bank_code: str = "") -> str:
    for code, bank in config.BANKS.items():
        if bank.account != account:
            continue
        if (not statement_format or statement_format == bank.format) and (
            not bank_code or bank_code == bank.bank_code
        ):
            return code
    raise BankParseError(f"unknown statement or payer account: {account}")


def _cents(value: int) -> Decimal:
    return Decimal(value).scaleb(-2)


def _lines(text: str) -> list[str]:
    # Also accept LF when a caller passes text through universal newline decoding.
    lines = text.replace("\r\n", "\n").removesuffix("\n").split("\n")
    if any("\r" in line for line in lines):
        raise BankParseError("invalid line ending")
    return lines


def _transaction(statement: dict, line_no: int, **fields) -> dict:
    tx_id = f"{statement['bank']}-{statement['statement_date']:%Y%m%d}-{line_no:04d}"
    return {**statement, "tx_id": tx_id, "line_no": line_no, **fields}


_SOURCES = {"bank_gpc": "ascii", "bank_sta": "cp852", "bank_txt": "utf-8", "kpc": "ascii"}
_TABLES = ("bank_transactions", "bank_tx_details", "payment_orders")
_RAW_SUFFIX = re.compile(r"__[0-9]{14}$")
_FILES_PER_PARTITION = 200


def _path_key(path: str) -> str:
    uri = urlsplit(path)
    if uri.scheme in ("file", "hdfs"):
        return unquote(uri.path)
    return path


def _parse_file(source: str, path: str, data: bytes) -> list[tuple]:
    from processing.bank import gpc, kpc, sta, txt

    stem = _RAW_SUFFIX.sub("", PurePosixPath(_path_key(path)).stem)
    try:
        text = data.decode(_SOURCES[source])
        if source == "kpc":
            return [("payment_orders", row) for row in kpc.parse(text, stem, path)]
        if source == "bank_txt":
            return [("companion", (stem, (path, txt.parse(text))))]
        parser = gpc if source == "bank_gpc" else sta
        _, transactions = parser.parse(text, path)
        tx_ids = {row["line_no"]: row["tx_id"] for row in transactions}
        return [("statement", (stem, tx_ids)), *(("bank_transactions", row) for row in transactions)]
    except (BankParseError, UnicodeDecodeError) as exc:
        return [("issue", _issue(source, path, str(exc)))]


def _issue(source: str, path: str, detail: str) -> tuple:
    return "PARSE_ERROR", source, path, None, detail


def _pair_details(pair: tuple) -> list[tuple]:
    tx_ids, (path, details) = pair[1]
    if tx_ids.keys() != details.keys():
        return [("issue", _issue("bank_txt", path, "TXT line numbers do not match statement"))]
    return [
        ("bank_tx_details", {"tx_id": tx_ids[line], "detail_text": detail, "source_file": path})
        for line, detail in details.items()
    ]


def run(spark: SparkSession, inputs: dict[str, list[str]] | None = None) -> dict[str, int]:
    """Parse current raw bank files or explicit fixture paths and replace the clean tables."""
    from common import dq, lake, schemas, tables

    if inputs is None:
        inputs = {
            source: [
                row.raw_path for row in lake.current_raw_files(spark, source).select("raw_path").collect()
            ]
            for source in _SOURCES
        }

    sc = spark.sparkContext
    paths = {}
    for source in _SOURCES:
        for path in inputs.get(source, ()):
            key = _path_key(path)
            reference = key if path.startswith("hdfs://") else path
            paths[key] = (source, reference, path)
    lookup = sc.broadcast(paths)

    def parse_binary(record):
        key, data = record
        source, reference, _ = lookup.value[_path_key(key)]
        return _parse_file(source, reference, bytes(data))

    batches = list(paths.values())
    files = [
        sc.binaryFiles(",".join(path for _, _, path in batches[start : start + _FILES_PER_PARTITION]))
        for start in range(0, len(batches), _FILES_PER_PARTITION)
    ]
    records = (sc.union(files).flatMap(parse_binary) if files else sc.parallelize([], 1)).cache()

    def rows(kind):
        return records.filter(lambda record: record[0] == kind).values()

    # An invalid statement emits no join key, so its TXT cannot create orphan details.
    paired = rows("statement").join(rows("companion")).flatMap(_pair_details).cache()
    try:
        counts = {}
        for table in _TABLES:
            schema = ", ".join(f"{name} {data_type}" for name, data_type in schemas.CLEAN_TABLES[table])
            data = (
                paired.filter(lambda row: row[0] == "bank_tx_details").values()
                if table == "bank_tx_details"
                else rows(table)
            )
            df = spark.createDataFrame(data, schema)
            tables.write_table(spark, df, table)
            counts[table] = df.count()
        issues = rows("issue").union(paired.filter(lambda row: row[0] == "issue").values())
        counts["issues"] = dq.write_issues(spark, spark.createDataFrame(issues, dq.ISSUE_SCHEMA), job="bank")
        return counts
    finally:
        paired.unpersist()
        records.unpersist()
        lookup.destroy()
