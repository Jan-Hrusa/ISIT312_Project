"""The one way to get a Spark session in jobs, generators and notebooks."""

from __future__ import annotations

import os

from pyspark.sql import SparkSession


def get_spark(app_name: str, master: str | None = None, hive: bool = True) -> SparkSession:
    """Return a Spark session with the project's settings.

    master: `SPARK_MASTER` from the environment if not given, default `local[*]` (use `yarn` for E1/E5).
    hive: Hive support (the metastore of the Docker stack) for every job that reads or writes lake tables;
    hive=False uses the in-memory catalog (the stack's spark-defaults.conf would otherwise select Hive).
    Unit tests use the fixtures in tests/conftest.py instead, never this function.
    """
    builder = (
        SparkSession.builder.appName(app_name)
        .master(master or os.environ.get("SPARK_MASTER", "local[*]"))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.sources.default", "orc")
        .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
        .config("hive.exec.dynamic.partition.mode", "nonstrict")
    )
    if hive:
        builder = builder.enableHiveSupport()
    else:
        builder = builder.config("spark.sql.catalogImplementation", "in-memory")
    return builder.getOrCreate()
