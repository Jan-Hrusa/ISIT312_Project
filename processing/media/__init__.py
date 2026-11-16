"""Pipeline step "media": file every photo and video to its project and describe every project document.

`run(spark, inputs=None)` reads the photos from their daily SequenceFiles (Task 18) and the videos and
documents from the raw zone, all through the ingest log (`common.lake.current_raw_files`), and writes
`media_files`, `documents` and the job's data-quality issues (NO_GPS, UNASSIGNED_PHOTO, WRONG_VERSION).
Rules: filing.py (photos), documents.py (videos and documents).
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    BooleanType,
    DateType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

from common import config, dq, lake, schemas, tables
from processing.media import documents, exif, filing

__all__ = ["run"]

JOB = "media"
FILE_ID_LENGTH = 16

_HDFS_PREFIX_RE = re.compile(r"^hdfs://[^/]+")
_HIVE_TO_SPARK = {
    "STRING": StringType(),
    "DOUBLE": DoubleType(),
    "BIGINT": LongType(),
    "BOOLEAN": BooleanType(),
    "DATE": DateType(),
    "TIMESTAMP": TimestampType(),
}


def run(spark: SparkSession, inputs: dict | None = None) -> dict[str, int]:
    """Recompute `media_files`, `documents` and the `media` issues; return their row counts.

    inputs: None reads the current files of the ingest log. Tests pass
    `{"photos": [(seq_path, key), ...], "video": [path, ...], "docs": [path, ...]}` (a missing source = none).
    """
    sites = filing.sites_from_projects(tables.read_table(spark, "projects").collect())

    photo_rdd = _photos(spark, inputs, sites).cache()
    try:
        media_rows = photo_rdd.map(lambda r: r[0])
        issues = photo_rdd.flatMap(lambda r: [r[1]] if r[1] is not None else []).collect()
        media = spark.createDataFrame(media_rows, _schema("media_files"))
        videos = spark.createDataFrame(_videos(spark, inputs), _schema("media_files"))
        media = media.unionByName(videos)

        docs = _documents(spark, inputs)
        issues += [
            ("WRONG_VERSION", "docs", f"{project}/{documents.DRAWING_STEM}", project, detail)
            for project, detail in documents.wrong_versions(docs)
        ]
        docs_df = spark.createDataFrame(
            [tuple(d[c] for c, _ in schemas.CLEAN_TABLES["documents"]) for d in docs], _schema("documents")
        )

        tables.write_table(spark, media, "media_files")
        tables.write_table(spark, docs_df, "documents")
        written_issues = dq.write_issues(spark, dq.issue_rows(spark, issues), JOB)
        return {
            "media_files": tables.read_table(spark, "media_files").count(),
            "documents": len(docs),
            "issues": written_issues,
        }
    finally:
        photo_rdd.unpersist()


def _photos(spark: SparkSession, inputs: dict | None, sites: list[filing.Site]):
    """RDD of (media_files row, issue or None) for every current photo."""
    wanted: dict[str, list[tuple[str, str | None]]] = {}
    if inputs is not None:
        for seq_path, key in inputs.get("photos", []):
            wanted.setdefault(key, []).append((_strip_hdfs_scheme(seq_path), None))
    else:
        rows = lake.current_raw_files(spark, "photos").select("raw_path", "seq_key", "sha256").collect()
        for r in rows:
            wanted.setdefault(r.seq_key, []).append((_strip_hdfs_scheme(r.raw_path), r.sha256))
    seq_paths = sorted({path for entries in wanted.values() for path, _ in entries})
    sc = spark.sparkContext
    if not seq_paths:
        return sc.emptyRDD()
    wanted_b = sc.broadcast(wanted)
    sites_b = sc.broadcast(sites)

    def process(records):
        for key, value in records:
            data = bytes(value)
            sha = hashlib.sha256(data).hexdigest()
            # A key can be in two SequenceFiles (a re-sent photo): the logged checksum picks the current one.
            match = [path for path, digest in wanted_b.value.get(key, []) if digest is None or digest == sha]
            if not match:
                continue
            yield _photo_record(key, data, sha, match[0], sites_b.value)

    return sc.sequenceFile(",".join(seq_paths)).mapPartitions(process)


def _photo_record(key: str, data: bytes, sha: str, raw_path: str, sites: list[filing.Site]):
    meta = exif.read(data)
    filed = filing.file_photo(meta.taken_at, meta.lat, meta.lon, sites)
    file_id = sha[:FILE_ID_LENGTH]
    row = (
        file_id,
        "PHOTO",
        key,
        meta.taken_at,
        meta.lat,
        meta.lon,
        len(data),
        meta.device,
        filed.project_code,
        filed.filing_rule,
        filed.distance_m,
        raw_path,
        key,
    )
    taken = meta.taken_at.strftime("%Y-%m-%d %H:%M:%S") if meta.taken_at else "unknown time"
    issue = None
    if meta.lat is None or meta.lon is None:
        issue = ("NO_GPS", "photos", file_id, None, f"{key} taken {taken}")
    elif filed.project_code == config.UNASSIGNED:
        nearest = filing.nearest_project(meta.lat, meta.lon, sites)
        where = f"{filed.distance_m:.0f} m from {nearest}" if nearest else "no signed project"
        issue = ("UNASSIGNED_PHOTO", "photos", file_id, None, f"{key} taken {taken}, {where}")
    return row, issue


def _videos(spark: SparkSession, inputs: dict | None) -> list[tuple]:
    rows = []
    for f in _raw_files(spark, inputs, "video"):
        day = documents.video_date(f["original_path"])
        rows.append(
            (
                f["sha256"][:FILE_ID_LENGTH],
                "VIDEO",
                Path(f["original_path"]).name,
                datetime.combine(day, time.min, tzinfo=timezone.utc),
                None,
                None,
                f["size_bytes"],
                None,
                documents.project_from_folder(f["original_path"], videos=True),
                filing.RULE_FOLDER,
                None,
                f["raw_path"],
                None,
            )
        )
    return rows


def _documents(spark: SparkSession, inputs: dict | None) -> list[dict]:
    docs = []
    for f in _raw_files(spark, inputs, "docs"):
        d = documents.describe(f["original_path"], f["business_date"], f["size_bytes"])
        d["file_id"] = f["sha256"][:FILE_ID_LENGTH]
        d["raw_path"] = f["raw_path"]
        docs.append(d)
    return docs


def _raw_files(spark: SparkSession, inputs: dict | None, source: str) -> list[dict]:
    """original_path, raw_path, business_date, size_bytes and sha256 of every current file of a source."""
    if inputs is None:
        return [
            {
                "original_path": r.original_path,
                "raw_path": _strip_hdfs_scheme(r.raw_path),
                "business_date": r.business_date,
                "size_bytes": r.size_bytes,
                "sha256": r.sha256,
            }
            for r in lake.current_raw_files(spark, source).collect()
        ]
    files = []
    for p in inputs.get(source, []):
        local = _local_path(p)
        data = local.read_bytes()
        files.append(
            {
                "original_path": local.as_posix(),
                "raw_path": _strip_hdfs_scheme(p),
                "business_date": _mtime_date(local),
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return files


def _schema(table: str) -> StructType:
    return StructType(
        [
            StructField(name, _HIVE_TO_SPARK[hive_type], True)
            for name, hive_type in schemas.CLEAN_TABLES[table]
        ]
    )


def _strip_hdfs_scheme(path: str) -> str:
    return _HDFS_PREFIX_RE.sub("", path)


def _local_path(uri_or_path: str) -> Path:
    if uri_or_path.startswith("file:"):
        return Path(unquote(urlparse(uri_or_path).path))
    return Path(uri_or_path)


def _mtime_date(path: Path) -> date:
    """The business date of a test fixture: the UTC date of its mtime (12:00 UTC, set by make_sources)."""
    return datetime.fromtimestamp(os.stat(path).st_mtime, tz=timezone.utc).date()
