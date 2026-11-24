"""Collection into the raw zone: the pipeline step `collect`."""

from __future__ import annotations

from datetime import datetime, timezone

from pyspark.sql import SparkSession


def run(spark: SparkSession) -> dict[str, int]:
    """Collect new files, snapshot the raw zone and prune old snapshots."""
    from common import lake
    from ingest import snapshot
    from ingest.collect import collect

    ingested_at = datetime.now(timezone.utc).replace(microsecond=0)
    stats = collect(spark, ingested_at=ingested_at)

    snapshot_count = 0

    if snapshot.config.DATASET != "x10":
        snapshot.ensure_snapshottable(spark)

        if snapshot.take(spark, ingested_at.strftime(lake.INGEST_TS_FORMAT)):
            snapshot_count = 1
            snapshot.prune(spark)

    return {
        "files_new": sum(counts["new"] for counts in stats.values()),
        "files_skipped": sum(counts["skipped"] for counts in stats.values()),
        "snapshot": snapshot_count,
    }
