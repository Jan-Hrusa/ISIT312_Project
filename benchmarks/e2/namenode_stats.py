"""NameNode numbers for experiment E2: namespace objects and heap from the NameNode's JMX servlet, plus
`hdfs dfs -count` and the `hdfs fsck` summary of one folder.

    python -m benchmarks.e2.namenode_stats /bench/x10/loose     # prints the numbers as JSON

`NAMENODE_JMX` (default http://namenode:9870/jmx, the stack's NameNode seen from the client container)
overrides the servlet address.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request

NAMENODE_JMX = os.environ.get("NAMENODE_JMX", "http://namenode:9870/jmx")
FS_NAMESYSTEM = "Hadoop:service=NameNode,name=FSNamesystem"
JVM_METRICS = "Hadoop:service=NameNode,name=JvmMetrics"
BYTES_PER_OBJECT = 150  # rule of thumb: every file, directory and block costs the NameNode about 150 bytes


def parse_jmx(payload: dict) -> dict:
    """FilesTotal, BlocksTotal and MemHeapUsedM from the servlet's JSON (`{"beans": [...]}`).

    FilesTotal counts every inode of the namespace: files and directories.
    """
    beans = {bean.get("name"): bean for bean in payload.get("beans", [])}
    try:
        fs, jvm = beans[FS_NAMESYSTEM], beans[JVM_METRICS]
        return {
            "files_total": int(fs["FilesTotal"]),
            "blocks_total": int(fs["BlocksTotal"]),
            "heap_mb": float(jvm["MemHeapUsedM"]),
        }
    except KeyError as missing:
        raise ValueError(f"NameNode JMX answer without {missing}") from None


def jmx(url: str = NAMENODE_JMX) -> dict:
    """The NameNode's current FilesTotal, BlocksTotal and MemHeapUsedM."""
    payload = {"beans": []}
    for query in (FS_NAMESYSTEM, JVM_METRICS):
        with urllib.request.urlopen(f"{url}?qry={query}", timeout=30) as response:
            payload["beans"].extend(json.load(response).get("beans", []))
    return parse_jmx(payload)


def parse_count(output: str) -> dict:
    """`hdfs dfs -count <dir>` -> dirs (the folder itself included), files, bytes."""
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 4 and all(f.isdigit() for f in fields[:3]):
            return {"dirs": int(fields[0]), "files": int(fields[1]), "bytes": int(fields[2])}
    raise ValueError(f"unexpected hdfs dfs -count output: {output!r}")


_FSCK = {
    "files": re.compile(r"Total files:\s+(\d+)"),
    "dirs": re.compile(r"Total dirs:\s+(\d+)"),
    "blocks": re.compile(r"Total blocks \(validated\):\s+(\d+)"),
    "bytes": re.compile(r"Total size:\s+(\d+)\s*B"),
}


def parse_fsck(output: str) -> dict:
    """The summary of `hdfs fsck <dir>`: files, dirs, blocks, bytes; and whether it is HEALTHY."""
    stats = {}
    for key, pattern in _FSCK.items():
        match = pattern.search(output)
        if match is None:
            raise ValueError(f"hdfs fsck output without {key!r}")
        stats[key] = int(match.group(1))
    stats["healthy"] = "is HEALTHY" in output
    return stats


def run_hdfs(*args: str) -> str:
    """Run an `hdfs` command (on the client container's PATH) and return its standard output."""
    done = subprocess.run(["hdfs", *args], capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"hdfs {' '.join(args)} failed: {done.stderr.strip()[-2000:]}")
    return done.stdout


def dir_stats(path: str) -> dict:
    """Objects of one folder: `hdfs dfs -count` (dirs, files, bytes) and `hdfs fsck` (blocks, health).

    fsck runs without `-files -blocks`: the summary is the same, without one output line per file (about
    300,000 of them for the loose x10 photos).
    """
    count = parse_count(run_hdfs("dfs", "-count", path))
    fsck = parse_fsck(run_hdfs("fsck", path))
    return {**count, "blocks": fsck["blocks"], "healthy": fsck["healthy"]}


def objects(stats: dict) -> int:
    """NameNode objects of a folder: files + directories + blocks."""
    return stats["files"] + stats["dirs"] + stats["blocks"]


def estimated_mb(stats: dict) -> float:
    """The rule-of-thumb NameNode memory for a folder's objects, in MB."""
    return objects(stats) * BYTES_PER_OBJECT / 1_000_000


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    report = {"namenode": jmx()}
    for path in args:
        stats = dir_stats(path)
        report[path] = {**stats, "objects": objects(stats), "estimated_mb": round(estimated_mb(stats), 1)}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
