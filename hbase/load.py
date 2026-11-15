"""Pipeline step "catalogue": load `media_files` and `documents` into the HBase table `media_catalog`.

A full reload: the table is dropped and created again, then every photo, video, document and drawing is put
with `catalogue.row_key` and `catalogue.cells` (formats of hbase/schema.md). Photos are read once more from
their SequenceFiles for the 96x72 thumbnail. Each Spark partition writes through its own happybase connection
in batches of BATCH_SIZE rows.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timezone
from pathlib import PurePosixPath

from pyspark.sql import SparkSession

from common import config, tables
from hbase import catalogue
from processing.media import documents, thumbs

BATCH_SIZE = 1000
# The key time of a photo whose EXIF has no capture time: it sorts before every dated photo of its project.
UNKNOWN_TIME = datetime(1970, 1, 1, tzinfo=timezone.utc)


def run(spark: SparkSession) -> dict[str, int]:
    """Reload the catalogue from the clean tables; return {"rows": rows written}."""
    conn = catalogue.connect()
    try:
        catalogue.create_table(conn, drop=True)
    finally:
        conn.close()

    sc = spark.sparkContext
    media = tables.read_table(spark, "media_files")
    videos = media.where("kind = 'VIDEO'").rdd.map(lambda r: _video_row(r.asDict()))
    docs = tables.read_table(spark, "documents").rdd.map(lambda r: _document_row(r.asDict()))
    rows = sc.union([_photo_rows(spark, media), videos, docs]).cache()
    try:
        count = rows.count()
        host, port, table = config.HBASE_HOST, config.HBASE_PORT, config.HBASE_TABLE
        rows.foreachPartition(lambda part: _put_partition(part, host, port, table))
    finally:
        rows.unpersist()
    return {"rows": count}


def _photo_rows(spark: SparkSession, media):
    """RDD of (row key, cells) for every photo, with its thumbnail from the SequenceFile."""
    sc = spark.sparkContext
    photos = [r.asDict() for r in media.where("kind = 'PHOTO'").collect()]
    if not photos:
        return sc.emptyRDD()
    by_key: dict[str, list[dict]] = {}
    for p in photos:
        by_key.setdefault(p["seq_key"], []).append(p)
    seq_paths = sorted({p["raw_path"] for p in photos})
    by_key_b = sc.broadcast(by_key)

    def build(records):
        for key, value in records:
            data = bytes(value)
            file_id = hashlib.sha256(data).hexdigest()[: catalogue.FILE_ID_LENGTH]
            for p in by_key_b.value.get(key, []):
                if p["file_id"] == file_id:
                    yield _photo_row(p, data)
                    break

    return sc.sequenceFile(",".join(seq_paths)).mapPartitions(build)


def _photo_row(p: dict, data: bytes) -> tuple[bytes, dict]:
    taken_at = p["taken_at"] or UNKNOWN_TIME
    families = {
        "meta": {
            "taken_at": p["taken_at"],
            "lat": p["lat"],
            "lon": p["lon"],
            "size_bytes": p["size_bytes"],
            "device": p["device"],
            "original_name": p["original_name"],
            "ext": PurePosixPath(p["original_name"]).suffix.lstrip(".").lower(),
            "filing_rule": p["filing_rule"],
        },
        "loc": {"raw_path": p["raw_path"], "seq_key": p["seq_key"]},
        "thumb": {"jpg": thumbs.thumbnail(data)},
    }
    key = catalogue.row_key(p["project_code"], "PHOTO", taken_at, p["file_id"])
    return key, catalogue.cells(families)


def _video_row(v: dict) -> tuple[bytes, dict]:
    families = {
        "meta": {
            "taken_at": v["taken_at"],
            "size_bytes": v["size_bytes"],
            "original_name": v["original_name"],
            "ext": PurePosixPath(v["original_name"]).suffix.lstrip(".").lower(),
            "filing_rule": v["filing_rule"],
        },
        "loc": {"raw_path": v["raw_path"]},
    }
    key = catalogue.row_key(v["project_code"], "VIDEO", _day_start(v["taken_at"].date()), v["file_id"])
    return key, catalogue.cells(families)


def _document_row(d: dict) -> tuple[bytes, dict]:
    name = _original_name(d["raw_path"])
    families = {
        "meta": {"size_bytes": d["size_bytes"], "original_name": name, "ext": d["ext"]},
        "loc": {"raw_path": d["raw_path"]},
        "doc": {
            "doc_type": d["doc_type"],
            "version": d["version"],
            "is_final": d["is_final"],
            "title": d["title"],
            "file_date": d["file_date"],
        },
    }
    kind = "DRAWING" if d["doc_type"] == documents.DRAWING else "DOC"
    key = catalogue.row_key(d["project_code"], kind, _day_start(d["file_date"]), d["file_id"])
    return key, catalogue.cells(families)


def _original_name(raw_path: str) -> str:
    """`contract.docx` from `/lake/raw/docs/<project>/<yyyy>/<mm>/contract__<ingest ts>.docx`."""
    p = PurePosixPath(raw_path)
    stem = p.stem.rsplit("__", 1)[0] if "__" in p.stem else p.stem
    return stem + p.suffix


def _day_start(day: date) -> datetime:
    """00:00:00 UTC of a date: the key time of videos, documents and drawings (contracts section 8)."""
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


def _put_partition(rows, host: str, port: int, table: str) -> None:
    import happybase

    conn = happybase.Connection(host=host, port=port, timeout=60_000)
    try:
        with conn.table(table).batch(batch_size=BATCH_SIZE) as batch:
            for key, cells in rows:
                batch.put(key, cells)
    finally:
        conn.close()
