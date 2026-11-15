"""Collection into the raw zone: the pipeline step `collect`."""

from __future__ import annotations

from pyspark.sql import SparkSession


def run(spark: SparkSession) -> dict[str, int]:
    """Collect every new source file into the raw zone; return the totals of the run."""
    from ingest.collect import collect

    stats = collect(spark)
    return {
        "files_new": sum(counts["new"] for counts in stats.values()),
        "files_skipped": sum(counts["skipped"] for counts in stats.values()),
    }
