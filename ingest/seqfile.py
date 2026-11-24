"""Hadoop SequenceFiles of photos: key `Text` = the photo's original file name, value `BytesWritable` = its
bytes (docs/contracts.md section 5).

`write_seq` writes one real file (not a Spark output folder) through the Hadoop API from PySpark, so a day's
photos become exactly one file in the raw zone; `read_seq` reads one back as an RDD. Paths without a scheme
resolve against `fs.defaultFS` (HDFS in the stack); the tests' `file://` paths use the local file system.
"""

from __future__ import annotations

from pyspark import RDD
from pyspark.sql import SparkSession

TEXT = "org.apache.hadoop.io.Text"
BYTES_WRITABLE = "org.apache.hadoop.io.BytesWritable"


def write_seq(spark: SparkSession, path: str, records: list[tuple[str, bytes]]) -> int:
    """Write `records` [(key, bytes), ...] in the given order as one SequenceFile at `path`; return the
    number written.

    The raw zone is write-once: an existing `path` is a FileExistsError, and if writing fails half-way the
    incomplete file (created by this call, logged nowhere) is removed before the error is raised.
    Parent folders are created. Records are not compressed: real JPEG bytes don't shrink, and Hadoop's default
    (zlib per record, used when no compression type is given) would cost CPU on every write and read.
    """
    sc = spark.sparkContext
    jvm = sc._jvm
    conf = sc._jsc.hadoopConfiguration()
    target = jvm.org.apache.hadoop.fs.Path(path)
    fs = target.getFileSystem(conf)
    if fs.exists(target):
        raise FileExistsError(f"{path} already exists (the raw zone is write-once)")
    fs.mkdirs(target.getParent())

    io = jvm.org.apache.hadoop.io
    no_compression = getattr(io, "SequenceFile$CompressionType").NONE
    writer = io.SequenceFile.createWriter(
        fs, conf, target, io.Text().getClass(), io.BytesWritable().getClass(), no_compression
    )
    written = 0
    try:
        for key, data in records:
            writer.append(io.Text(key), io.BytesWritable(bytearray(data)))
            written += 1
    except BaseException:
        writer.close()
        fs.delete(target, False)
        raise
    writer.close()
    return written


def read_seq(spark: SparkSession, path: str) -> RDD:
    """The records of a SequenceFile as an RDD of (key str, value bytes)."""
    rdd = spark.sparkContext.sequenceFile(path, TEXT, BYTES_WRITABLE)
    return rdd.map(lambda record: (record[0], bytes(record[1])))
