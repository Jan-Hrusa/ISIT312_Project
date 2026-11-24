"""HDFS helpers through Spark's JVM (Hadoop FileSystem API), so thousands of files need no `hdfs` command
each.

Paths without a scheme resolve against `fs.defaultFS` (hdfs://namenode:8020 in the stack). A path with its
own scheme (the tests' `file://` lake folder) uses that file system.
"""

from __future__ import annotations

from pathlib import Path

from pyspark.sql import SparkSession


def _conf(spark: SparkSession):
    return spark.sparkContext._jsc.hadoopConfiguration()


def _resolve(spark: SparkSession, path: str):
    """(FileSystem, Path) of `path`: its own file system if it has a scheme, else `fs.defaultFS`."""
    hadoop_path = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(path)
    return hadoop_path.getFileSystem(_conf(spark)), hadoop_path


def fs(spark: SparkSession):
    """The Hadoop FileSystem (py4j object) for `fs.defaultFS` of the session's Hadoop configuration."""
    return spark.sparkContext._jvm.org.apache.hadoop.fs.FileSystem.get(_conf(spark))


def put(spark: SparkSession, local_path: str, hdfs_path: str) -> None:
    """Copy a local file to `hdfs_path` (parent folders created). An existing target is an error
    (FileExistsError): the raw zone is write-once."""
    file_system, target = _resolve(spark, hdfs_path)
    if file_system.exists(target):
        raise FileExistsError(f"{hdfs_path} already exists (the raw zone is write-once)")
    source = spark.sparkContext._jvm.org.apache.hadoop.fs.Path(Path(local_path).resolve().as_uri())
    # delSrc=False, overwrite=False: a target created since the check above still fails in Hadoop.
    file_system.copyFromLocalFile(False, False, source, target)


def exists(spark: SparkSession, path: str) -> bool:
    """True if the file or folder exists."""
    file_system, hadoop_path = _resolve(spark, path)
    return bool(file_system.exists(hadoop_path))


def mkdirs(spark: SparkSession, path: str) -> None:
    """Create a folder and its parents; no error if it exists."""
    file_system, hadoop_path = _resolve(spark, path)
    file_system.mkdirs(hadoop_path)


def ls(spark: SparkSession, path: str) -> list[str]:
    """Full paths of the entries directly in a folder, sorted.

    In the form of `path`: without a scheme when `path` has none (raw paths never carry one), as full URIs
    when it has one.
    """
    file_system, hadoop_path = _resolve(spark, path)
    with_scheme = hadoop_path.toUri().getScheme() is not None
    entries = [status.getPath() for status in file_system.listStatus(hadoop_path)]
    return sorted(str(p.toString()) if with_scheme else str(p.toUri().getPath()) for p in entries)


def read_bytes(spark: SparkSession, path: str) -> bytes:
    """The whole content of a file."""
    file_system, hadoop_path = _resolve(spark, path)
    stream = file_system.open(hadoop_path)
    try:
        return bytes(spark.sparkContext._jvm.org.apache.commons.io.IOUtils.toByteArray(stream))
    finally:
        stream.close()


def allow_snapshot(spark: SparkSession, dir: str) -> None:
    """Make `dir` snapshottable, through `org.apache.hadoop.hdfs.client.HdfsAdmin.allowSnapshot`
    (not FileSystem). No error if it already is."""
    file_system, hadoop_path = _resolve(spark, dir)
    admin = spark.sparkContext._jvm.org.apache.hadoop.hdfs.client.HdfsAdmin(
        file_system.getUri(), _conf(spark)
    )
    admin.allowSnapshot(hadoop_path)


def create_snapshot(spark: SparkSession, dir: str, name: str) -> str:
    """Create snapshot `name` of `dir`; return its path `<dir>/.snapshot/<name>`."""
    file_system, hadoop_path = _resolve(spark, dir)
    file_system.createSnapshot(hadoop_path, name)
    return f"{dir.rstrip('/')}/.snapshot/{name}"


def list_snapshots(spark: SparkSession, dir: str) -> list[str]:
    """Names of the snapshots of `dir` (= listStatus('<dir>/.snapshot')), sorted."""
    file_system, hadoop_path = _resolve(spark, f"{dir.rstrip('/')}/.snapshot")
    return sorted(str(status.getPath().getName()) for status in file_system.listStatus(hadoop_path))


def delete_snapshot(spark: SparkSession, dir: str, name: str) -> None:
    """Delete snapshot `name` of `dir`."""
    file_system, hadoop_path = _resolve(spark, dir)
    file_system.deleteSnapshot(hadoop_path, name)
