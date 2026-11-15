"""Raw-zone rules: raw paths, the ingest log and the current file list per source (docs/contracts.md
section 5). The collection job (ingest/collect.py) writes through them; every parser reads its input list
from `current_raw_files`.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import PurePosixPath

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F

from common import config
from common.schemas import CLEAN_TABLES
from common.tables import qualified_name

# Columns returned by current_raw_files.
CURRENT_FILE_COLUMNS = ("original_path", "raw_path", "seq_key", "size_bytes", "sha256", "business_date")

INGEST_TS_FORMAT = "%Y%m%d%H%M%S"


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
    `<LAKE_RAW>/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq`): asking for a photo path is a ValueError too.
    """
    _check_source(source)
    if source == "photos":
        raise ValueError("photos have no raw path of their own: they are packed into daily SequenceFiles")
    if config.RAW_SOURCES[source].keep_project:
        if not project:
            raise ValueError(f"source {source} needs a project for its raw path")
        folder = f"{config.LAKE_RAW}/{source}/{project}"
    else:
        if project:
            raise ValueError(f"source {source} doesn't keep a project in its raw path, got {project!r}")
        folder = f"{config.LAKE_RAW}/{source}"
    name = PurePosixPath(original_name)
    stamp = ingested_at.strftime(INGEST_TS_FORMAT)
    return f"{folder}/{business_date:%Y}/{business_date:%m}/{name.stem}__{stamp}{name.suffix}"


def append_ingest_log(spark: SparkSession, rows: list[dict]) -> int:
    """Append rows to `<CLEAN_DB>.ingest_log` (never overwrite); return the number appended.

    Each row has the ingest_log columns of common/schemas.py (`seq_key` None except for photos):
    `run_id` = the run's start in UTC as `yyyyMMddHHmmss` (also the snapshot name `raw-<run_id>`);
    `original_path` relative to `SOURCES_DIR` with `/` separators
    (e.g. `mailbox/photos/IMG_20240512_101500_00042.jpg`);
    `business_date` = the UTC date of the file's mtime; `ingested_at` = UTC timestamp.
    A row without one of the columns is a ValueError (`seq_key` may be left out).
    """
    if not rows:
        return 0
    columns = CLEAN_TABLES["ingest_log"]
    names = [name for name, _ in columns]
    required = [name for name in names if name != "seq_key"]
    for row in rows:
        missing = [name for name in required if row.get(name) is None]
        if missing:
            raise ValueError(f"ingest_log row without {', '.join(missing)}: {row.get('original_path')!r}")
    schema = ", ".join(f"{name} {hive_type}" for name, hive_type in columns)
    df = spark.createDataFrame([tuple(row.get(name) for name in names) for row in rows], schema)
    # One file per run: the log is read on every run and by every parser.
    df.coalesce(1).write.insertInto(qualified_name("ingest_log"), overwrite=False)
    return len(rows)


def current_raw_files(spark: SparkSession, source: str) -> DataFrame:
    """The current version of every file of `source`: per `original_path` (and `seq_key` for photos) the
    ingest_log row with the latest `ingested_at`. Columns CURRENT_FILE_COLUMNS.

    Every parser takes its input list from here, never by listing raw folders.
    """
    _check_source(source)
    latest_first = Window.partitionBy("original_path", "seq_key").orderBy(
        F.col("ingested_at").desc(), F.col("raw_path").desc()
    )
    return (
        spark.table(qualified_name("ingest_log"))
        .where(F.col("source") == source)
        .withColumn("_version", F.row_number().over(latest_first))
        .where(F.col("_version") == 1)
        .select(*CURRENT_FILE_COLUMNS)
    )


def _check_source(source: str) -> None:
    if source not in config.RAW_SOURCES:
        raise ValueError(f"unknown source: {source}")
