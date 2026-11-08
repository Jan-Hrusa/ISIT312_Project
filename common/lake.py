"""Raw-zone rules: raw paths, the ingest log and the current file list per source. Signatures fixed in
Task 2; Ryan implements them in Task 14.1 (docs/contracts.md section 5).

Each function raises NotImplementedError until Task 14.1 is merged.
"""

from __future__ import annotations

from datetime import date, datetime

from pyspark.sql import DataFrame, SparkSession

_LATER = "implemented in Task 14.1 (common/lake.py)"

# Columns returned by current_raw_files.
CURRENT_FILE_COLUMNS = ("original_path", "raw_path", "seq_key", "size_bytes", "sha256", "business_date")


def raw_path(
    source: str,
    business_date: date,
    original_name: str,
    ingested_at: datetime,
    project: str | None = None,
) -> str:
    """Where a collected file goes in the raw zone.

    `<LAKE_RAW>/<source>/<yyyy>/<mm>/<stem>__<ingest UTC yyyyMMddHHmmss><ext>`, yyyy/mm from `business_date`
    (the file's mtime), stem and ext from `original_name`, e.g.
    `/lake/raw/bank_gpc/2026/01/26001_2101234567_CZK__20261114093000.gpc` (statement 26001 dated in January
    2026, collected on 14 Nov 2026). Raw paths never carry a scheme (no `hdfs://namenode:8020`).
    Sources with `keep_project` in `config.RAW_SOURCES` (`docs`, `video`) need `project` and put it after the
    source: `<LAKE_RAW>/docs/<project>/<yyyy>/<mm>/...`; missing project or a project for another source is a
    ValueError. Photos are not placed with this function (Task 18 packs them into daily SequenceFiles
    `<LAKE_RAW>/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq`).
    """
    raise NotImplementedError(_LATER)


def append_ingest_log(spark: SparkSession, rows: list[dict]) -> int:
    """Append rows to `<CLEAN_DB>.ingest_log` (never overwrite); return the number appended.

    Each row has the ingest_log columns of common/schemas.py (`seq_key` None except for photos):
    `run_id` = the run's start in UTC as `yyyyMMddHHmmss` (also the snapshot name `raw-<run_id>`);
    `original_path` relative to `SOURCES_DIR` with `/` separators
    (e.g. `mailbox/photos/IMG_20240512_101500_00042.jpg`);
    `business_date` = the UTC date of the file's mtime; `ingested_at` = UTC timestamp.
    """
    raise NotImplementedError(_LATER)


def current_raw_files(spark: SparkSession, source: str) -> DataFrame:
    """The current version of every file of `source`: per `original_path` (and `seq_key` for photos) the
    ingest_log row with the latest `ingested_at`. Columns CURRENT_FILE_COLUMNS.

    Every parser takes its input list from here, never by listing raw folders.
    """
    raise NotImplementedError(_LATER)
