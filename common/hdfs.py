"""HDFS helpers through Spark's JVM (Hadoop FileSystem API).

Signatures fixed in Task 2; Ryan implements them in Task 14.1.

Paths without a scheme resolve against `fs.defaultFS` (hdfs://namenode:8020 in the stack). Each function
raises NotImplementedError until Task 14.1 is merged.
"""

from __future__ import annotations

from pyspark.sql import SparkSession

_LATER = "implemented in Task 14.1 (common/hdfs.py)"


def fs(spark: SparkSession):
    """The Hadoop FileSystem (py4j object) for `fs.defaultFS` of the session's Hadoop configuration."""
    raise NotImplementedError(_LATER)


def put(spark: SparkSession, local_path: str, hdfs_path: str) -> None:
    """Copy a local file to `hdfs_path` (parent folders created). An existing target is an error
    (FileExistsError): the raw zone is write-once."""
    raise NotImplementedError(_LATER)


def exists(spark: SparkSession, path: str) -> bool:
    """True if the file or folder exists."""
    raise NotImplementedError(_LATER)


def mkdirs(spark: SparkSession, path: str) -> None:
    """Create a folder and its parents; no error if it exists."""
    raise NotImplementedError(_LATER)


def ls(spark: SparkSession, path: str) -> list[str]:
    """Full paths of the entries directly in a folder, sorted."""
    raise NotImplementedError(_LATER)


def read_bytes(spark: SparkSession, path: str) -> bytes:
    """The whole content of a file."""
    raise NotImplementedError(_LATER)


def allow_snapshot(spark: SparkSession, dir: str) -> None:
    """Make `dir` snapshottable, through `org.apache.hadoop.hdfs.client.HdfsAdmin.allowSnapshot`
    (not FileSystem). No error if it already is."""
    raise NotImplementedError(_LATER)


def create_snapshot(spark: SparkSession, dir: str, name: str) -> str:
    """Create snapshot `name` of `dir`; return its path `<dir>/.snapshot/<name>`."""
    raise NotImplementedError(_LATER)


def list_snapshots(spark: SparkSession, dir: str) -> list[str]:
    """Names of the snapshots of `dir` (= listStatus('<dir>/.snapshot')), sorted."""
    raise NotImplementedError(_LATER)


def delete_snapshot(spark: SparkSession, dir: str, name: str) -> None:
    """Delete snapshot `name` of `dir`."""
    raise NotImplementedError(_LATER)
