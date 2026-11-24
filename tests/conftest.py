"""Shared test fixtures. None of them reaches the Docker stack: local Spark, local files, a temporary Derby
metastore, so `pytest -m "not integration"` passes with the stack stopped.

- `spark`: local[2] Spark session with the in-memory catalog (DataFrame logic, no tables).
- `spark_hive`: local[2] Spark session with Hive support on a temporary Derby metastore (DDL, table
  writes).
- `clean_db`: `spark_hive` plus every clean table created in a temporary database and lake folder; the
  `common.config` names point there for the test.
- `fixtures_dir`: `tests/fixtures/`.
- `sources_tree`: a dated `sources/` tree built from `tests/fixtures/sources/` (see make_sources.py).

Only one Spark session can exist per process, so asking for `spark` after `spark_hive` (or the other way
round) stops the first one: a test may switch from one to the other, but must not use the first session again
after asking for the second.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from tests.fixtures.make_sources import make_sources

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

_COMMON_CONF = {
    "spark.ui.enabled": "false",
    "spark.sql.shuffle.partitions": "2",
    "spark.sql.session.timeZone": "UTC",
    "spark.sql.sources.default": "orc",
    "spark.sql.sources.partitionOverwriteMode": "dynamic",
    "hive.exec.dynamic.partition.mode": "nonstrict",
    # Never the stack's HDFS, even when HADOOP_CONF_DIR points at it (client container).
    "spark.hadoop.fs.defaultFS": "file:///",
}


class _SparkSessions:
    """Keeps at most one test Spark session alive and switches between the two kinds on demand."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.kind: str | None = None
        self.session = None

    def get(self, kind: str):
        from pyspark.sql import SparkSession

        if self.kind == kind:
            return self.session
        self.stop()
        builder = SparkSession.builder.master("local[2]").appName(f"tests-{kind}")
        for key, value in _COMMON_CONF.items():
            builder = builder.config(key, value)
        if kind == "memory":
            builder = builder.config("spark.sql.catalogImplementation", "in-memory").config(
                "spark.sql.warehouse.dir", (self.root / "memory-warehouse").as_uri()
            )
        else:
            metastore = self.root / "metastore_db"
            builder = (
                builder.enableHiveSupport()
                .config("spark.sql.warehouse.dir", (self.root / "hive-warehouse").as_uri())
                # Built-in Hive client on a local Derby metastore; overrides the stack's spark-defaults.conf
                # (metastore 3.1.3 jars, thrift://metastore:9083).
                .config("spark.sql.hive.metastore.version", "2.3.9")
                .config("spark.sql.hive.metastore.jars", "builtin")
                .config("spark.hadoop.hive.metastore.uris", "")
                .config(
                    "spark.hadoop.javax.jdo.option.ConnectionURL",
                    f"jdbc:derby:;databaseName={metastore};create=true",
                )
                .config("spark.hadoop.hive.metastore.schema.verification", "false")
                .config("spark.hadoop.datanucleus.schema.autoCreateAll", "true")
            )
        self.session = builder.getOrCreate()
        self.kind = kind
        return self.session

    def stop(self) -> None:
        if self.session is not None:
            self.session.stop()
        self.kind, self.session = None, None


@pytest.fixture(scope="session")
def _spark_sessions(tmp_path_factory):
    sessions = _SparkSessions(tmp_path_factory.mktemp("spark"))
    yield sessions
    sessions.stop()


@pytest.fixture
def spark(_spark_sessions):
    """Local Spark, in-memory catalog."""
    return _spark_sessions.get("memory")


@pytest.fixture
def spark_hive(_spark_sessions):
    """Local Spark with Hive support on a temporary Derby metastore."""
    return _spark_sessions.get("hive")


@pytest.fixture
def clean_db(spark_hive, tmp_path, monkeypatch):
    """Every clean table in a fresh database and lake folder (common.config redirected for this test)."""
    from common import config
    from common.tables import create_clean_tables

    lake = (tmp_path / "lake").as_uri()
    monkeypatch.setattr(config, "LAKE_ROOT", lake)
    monkeypatch.setattr(config, "LAKE_RAW", f"{lake}/raw")
    monkeypatch.setattr(config, "LAKE_CLEAN", f"{lake}/clean")
    monkeypatch.setattr(config, "LAKE_DW", f"{lake}/dw")
    monkeypatch.setattr(config, "CLEAN_DB", f"fve_clean_test_{uuid.uuid4().hex[:8]}")
    create_clean_tables(spark_hive)
    yield spark_hive
    spark_hive.sql(f"DROP DATABASE IF EXISTS {config.CLEAN_DB} CASCADE")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sources_tree(tmp_path) -> Path:
    """A dated copy of tests/fixtures/sources/ in a temporary folder."""
    return make_sources(tmp_path / "sources")
