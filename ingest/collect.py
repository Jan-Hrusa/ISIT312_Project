"""The collection job: every new file in `sources/` goes into the raw zone exactly once, unchanged, and is
logged in `ingest_log` (docs/contracts.md section 5).

Run it in the client container: `python -m ingest.collect [--sources photos video] [--dry-run]`
(`FVE_DATASET=x10` collects `sources_x10/` into `/bench/x10/lake`).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from common import config, hdfs, lake
from common.spark import get_spark
from common.tables import create_clean_tables, qualified_name

PHOTOS = "photos"
_PACKER_MODULE = "ingest.media_pack"
_HASH_CHUNK = 1024 * 1024
_COPY_THREADS = 8


def collect(
    spark: SparkSession,
    sources_dir: Path | str | None = None,
    sources: list[str] | None = None,
    dry_run: bool = False,
    ingested_at: datetime | None = None,
) -> dict[str, dict[str, int]]:
    """Collect the new files of `sources` (source keys of `config.RAW_SOURCES`; None = all) from
    `sources_dir` (None = `config.SOURCES_DIR`) and return `{source: {"new", "skipped", "bytes"}}`.

    A file is new when (source, original path, SHA-256) is not in `ingest_log` yet: an unchanged file is
    skipped, a changed one gets a new raw file, identical bytes at different paths are all collected.
    Photos are handed to Task 18's `ingest.media_pack.pack`, which packs them into daily SequenceFiles and
    returns their log rows; until that module is merged they are not read at all and reported as SKIPPED.
    Nothing under the raw zone is overwritten: an existing target path raises FileExistsError.
    `dry_run` only counts: no file is copied, no table created, nothing logged.
    """
    root = Path(sources_dir) if sources_dir is not None else Path(config.SOURCES_DIR)
    selected = list(config.RAW_SOURCES) if sources is None else list(sources)
    unknown = [s for s in selected if s not in config.RAW_SOURCES]
    if unknown:
        raise ValueError(f"unknown source: {', '.join(unknown)}")

    ingested_at = ingested_at or _now()
    run_id = ingested_at.strftime(lake.INGEST_TS_FORMAT)
    if not dry_run:
        _ensure_tables(spark)
    known = _known_files(spark, selected)
    pack = _photo_packer() if PHOTOS in selected else None
    packer_missing = PHOTOS in selected and pack is None

    stats = {source: {"new": 0, "skipped": 0, "bytes": 0} for source in selected}
    rows: list[dict] = []
    photos: list[dict] = []
    try:
        for source in selected:
            if source == PHOTOS and packer_missing:
                continue
            spec = config.RAW_SOURCES[source]
            copies: list[tuple[str, str, dict]] = []
            for path, info in _source_files(root, spec):
                original_path = path.relative_to(root).as_posix()
                sha256 = _sha256(path)
                if (source, original_path, sha256) in known:
                    stats[source]["skipped"] += 1
                    continue
                business_date = datetime.fromtimestamp(info.st_mtime, timezone.utc).date()
                if source == PHOTOS:
                    photos.append(
                        {
                            "local_path": str(path),
                            "original_path": original_path,
                            "business_date": business_date,
                            "sha256": sha256,
                            "size_bytes": info.st_size,
                        }
                    )
                    continue
                project = _project_of(path, root, spec) if spec.keep_project else None
                target = lake.raw_path(source, business_date, path.name, ingested_at, project=project)
                row = {
                    "run_id": run_id,
                    "source": source,
                    "original_path": original_path,
                    "raw_path": target,
                    "seq_key": None,
                    "size_bytes": info.st_size,
                    "sha256": sha256,
                    "business_date": business_date,
                    "ingested_at": ingested_at,
                }
                copies.append((str(path), target, row))
                stats[source]["new"] += 1
                stats[source]["bytes"] += info.st_size
            if not dry_run:
                _copy_files(spark, copies, rows)

        if photos:
            if not dry_run:
                rows.extend(pack(spark, photos, run_id, ingested_at))
            stats[PHOTOS]["new"] = len(photos)
            stats[PHOTOS]["bytes"] = sum(photo["size_bytes"] for photo in photos)
    finally:
        # Also after a failure: a file already copied must be logged, or the next run would copy it again
        # and no parser could find the first copy.
        if rows:
            lake.append_ingest_log(spark, rows)

    for source in selected:
        if source == PHOTOS and packer_missing:
            print(f"{PHOTOS}: SKIPPED (packer not merged)")
            continue
        counts = stats[source]
        megabytes = counts["bytes"] / 1_000_000
        print(f"{source}: {counts['new']} new, {counts['skipped']} skipped, {megabytes:.1f} MB")
    return stats


def _copy_files(spark: SparkSession, copies: list[tuple[str, str, dict]], rows: list[dict]) -> None:
    """Copy (local path, raw path, log row) entries into the raw zone on a few threads and add the row of
    every file that arrived to `rows`.

    Threads because HDFS spends most of a small file's write waiting for the NameNode to confirm it: on the
    stack one thread copies about 15 files a second, eight about 70. After a failure the copies not started
    yet are dropped, the running ones finish (and are logged), and the first error is raised.
    """

    def copy(entry: tuple[str, str, dict]) -> None:
        local_path, target, row = entry
        hdfs.put(spark, local_path, target)
        rows.append(row)

    pool = ThreadPoolExecutor(max_workers=_COPY_THREADS)
    try:
        for _ in pool.map(copy, copies):
            pass
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _now() -> datetime:
    """The run's start: UTC, whole seconds (run_id and the raw file names carry seconds)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _ensure_tables(spark: SparkSession) -> None:
    if not spark.catalog.tableExists(qualified_name("ingest_log")):
        create_clean_tables(spark)


def _known_files(spark: SparkSession, sources: list[str]) -> set[tuple[str, str, str]]:
    """(source, original_path, sha256) of everything collected so far for `sources`."""
    table = qualified_name("ingest_log")
    if not spark.catalog.tableExists(table):
        return set()
    logged = spark.table(table).where(F.col("source").isin(sources))
    return {
        (row.source, row.original_path, row.sha256)
        for row in logged.select("source", "original_path", "sha256").distinct().collect()
    }


def _source_files(root: Path, spec: config.RawSource) -> list[tuple[Path, os.stat_result]]:
    """The files of one source with their stat, in a stable order; names starting with "." (.gitkeep) are
    not data. One stat per file: on a bind-mounted sources folder every file operation is slow."""
    files = []
    for path in sorted((root / spec.folder).glob(spec.pattern)):
        if path.name.startswith("."):
            continue
        file_stat = path.stat()
        if stat.S_ISREG(file_stat.st_mode):
            files.append((path, file_stat))
    return files


def _project_of(path: Path, root: Path, spec: config.RawSource) -> str:
    """The project folder of a document or video: the first folder below the source's folder."""
    project = path.relative_to(root / spec.folder).parts[0]
    if not config.is_project_code(project):
        raise ValueError(f"{path.relative_to(root).as_posix()}: folder {project!r} is not a project code")
    return project


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _photo_packer():
    """Task 18's `pack(spark, files, run_id, ingested_at) -> list[dict]`, or None until it is merged."""
    if importlib.util.find_spec(_PACKER_MODULE) is None:
        return None
    return importlib.import_module(_PACKER_MODULE).pack


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Collect new source files into the raw zone.")
    parser.add_argument("--sources", nargs="+", choices=list(config.RAW_SOURCES), help="default: all sources")
    parser.add_argument("--dry-run", action="store_true", help="count only: copy and log nothing")
    args = parser.parse_args(argv)
    collect(get_spark("collect"), sources=args.sources, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
