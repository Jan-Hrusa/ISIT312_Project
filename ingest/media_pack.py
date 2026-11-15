"""Photo packing (Task 18): HDFS's small-files fix. Instead of one raw file per photo, each day's photos
become one SequenceFile `<LAKE_RAW>/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq`, and every photo gets an
`ingest_log` row saying which file and key hold it (docs/contracts.md section 5).

The collection job (ingest/collect.py) finds this module, hands it the new photos of a run (already
deduplicated against the log) and appends the returned rows with its own, so the next run skips them.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path, PurePosixPath

from pyspark.sql import SparkSession

from common import config, hdfs, lake
from ingest.seqfile import write_seq

SOURCE = "photos"
# Each daily file spends most of its write waiting for HDFS to create and close it (75-95 ms on the stack,
# whatever its size), so days are packed on a few threads, as collect copies loose files.
_PACK_THREADS = 8


def day_path(day: date) -> str:
    """The daily SequenceFile of `day`: `<LAKE_RAW>/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq`."""
    return f"{config.LAKE_RAW}/{SOURCE}/{day:%Y}/{day:%m}/{day:%Y-%m-%d}.seq"


def target_path(spark: SparkSession, day: date, ingested_at: datetime) -> str:
    """Where this run packs the photos of `day`: the daily file, or, if an earlier run already wrote it,
    `<yyyy-MM-dd>__<ingest ts>.seq` next to it (the raw zone is write-once)."""
    path = day_path(day)
    if not hdfs.exists(spark, path):
        return path
    return f"{path[: -len('.seq')]}__{ingested_at.strftime(lake.INGEST_TS_FORMAT)}.seq"


def pack(spark: SparkSession, files: list[dict], run_id: str, ingested_at: datetime) -> list[dict]:
    """Pack `files` into daily SequenceFiles; return one `ingest_log` row per photo.

    `files` are the dicts collect builds: `local_path`, `original_path` (e.g. `mailbox/photos/IMG_...jpg`),
    `business_date` (the file's mtime date, as for every source: the photo's day), `sha256`, `size_bytes`.
    Photos are grouped by `business_date`; each day's photos are written sorted by name, key = the original
    file name. A photo whose bytes no longer match its `sha256` (changed since collect hashed it) is a
    ValueError, raised before anything of its day is written.
    Each returned row has every ingest_log column: run_id, source "photos", original_path, raw_path = the
    SequenceFile, seq_key = the original name, size_bytes, sha256, business_date = the day, ingested_at.
    Rows come in day order, then by name.

    Days are packed on a few threads. If a day fails, the days not started are dropped, the running ones
    finish, the rows of every day already written are appended to `ingest_log` here (collect appends only
    what pack returns, and a file in the write-once raw zone must never be left unlogged), and the first
    error is raised.
    """
    by_day: dict[date, list[dict]] = defaultdict(list)
    for photo in files:
        by_day[photo["business_date"]].append(photo)

    def pack_day(day: date) -> list[dict]:
        photos = sorted(by_day[day], key=lambda p: (_name(p), p["original_path"]))
        records = [(_name(photo), _read_checked(photo)) for photo in photos]
        target = target_path(spark, day, ingested_at)
        write_seq(spark, target, records)
        return [
            {
                "run_id": run_id,
                "source": SOURCE,
                "original_path": photo["original_path"],
                "raw_path": target,
                "seq_key": _name(photo),
                "size_bytes": photo["size_bytes"],
                "sha256": photo["sha256"],
                "business_date": day,
                "ingested_at": ingested_at,
            }
            for photo in photos
        ]

    if not by_day:
        return []
    written: dict[date, list[dict]] = {}
    pool = ThreadPoolExecutor(max_workers=_PACK_THREADS)
    futures = {pool.submit(pack_day, day): day for day in sorted(by_day)}
    try:
        for future in as_completed(futures):
            written[futures[future]] = future.result()
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        for future, day in futures.items():
            if not future.cancelled() and future.exception() is None:
                written[day] = future.result()
        if written:
            lake.append_ingest_log(spark, _in_day_order(written))
        raise
    pool.shutdown(wait=True)
    return _in_day_order(written)


def _in_day_order(rows_by_day: dict[date, list[dict]]) -> list[dict]:
    return [row for day in sorted(rows_by_day) for row in rows_by_day[day]]


def _name(photo: dict) -> str:
    return PurePosixPath(photo["original_path"]).name


def _read_checked(photo: dict) -> bytes:
    data = Path(photo["local_path"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != photo["sha256"]:
        raise ValueError(f"{photo['original_path']} changed since it was hashed: collect it again")
    return data
