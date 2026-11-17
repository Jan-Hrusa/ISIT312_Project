"""HDFS snapshots of the raw zone."""

from __future__ import annotations

from pyspark.sql import SparkSession

from common import config, hdfs

SNAPSHOT_PREFIX = "raw-"
DEFAULT_KEEP = 30


def ensure_snapshottable(spark: SparkSession) -> None:
    """Enable snapshots on the raw zone."""
    hdfs.allow_snapshot(spark, config.LAKE_RAW)


def take(spark: SparkSession, run_id: str) -> str:
    """Create the raw-zone snapshot for this collection run.

    Returns the snapshot path, or an empty string for the x10 dataset.
    """
    if config.DATASET == "x10":
        return ""

    name = f"{SNAPSHOT_PREFIX}{run_id}"
    return hdfs.create_snapshot(spark, config.LAKE_RAW, name)


def prune(spark: SparkSession, keep: int = DEFAULT_KEEP) -> None:
    """Keep only the newest `keep` raw-zone snapshots."""
    if keep < 0:
        raise ValueError("keep must be non-negative")

    snapshots = sorted(
        name for name in hdfs.list_snapshots(spark, config.LAKE_RAW)
        if name.startswith(SNAPSHOT_PREFIX)
    )

    for name in snapshots[:-keep] if keep else snapshots:
        hdfs.delete_snapshot(spark, config.LAKE_RAW, name)
