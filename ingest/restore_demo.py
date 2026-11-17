"""Demonstrate restoring a project's raw documents from an HDFS snapshot.

This is the only code allowed to delete under the raw zone, and only the demo project's documents folder. The
snapshot is chosen and compared with the live folder before anything is deleted, so the demo never removes
files it can't bring back.
"""

from __future__ import annotations

import argparse
import re
import subprocess

from py4j.protocol import Py4JJavaError

from common import config, hdfs
from common.projects import load_projects
from common.spark import get_spark
from ingest.snapshot import SNAPSHOT_PREFIX


def _files_with_checksums(spark, root: str) -> dict[str, str]:
    """Recursively list the files under `root` as {path relative to `root`: HDFS file checksum}."""
    fs, root_path = hdfs._resolve(spark, root)
    base = str(fs.makeQualified(root_path).toUri().getPath()).rstrip("/")
    results = {}

    def visit(path):
        for status in fs.listStatus(path):
            child = status.getPath()
            if status.isDirectory():
                visit(child)
            else:
                relative = str(child.toUri().getPath())[len(base) + 1 :]
                results[relative] = str(fs.getFileChecksum(child))

    if fs.exists(root_path):
        visit(root_path)

    return dict(sorted(results.items()))


def _print_listing(title: str, files: dict[str, str]) -> None:
    print(f"{title}: {len(files)} files", flush=True)
    for path, checksum in files.items():
        print(f"  {checksum}  {path}", flush=True)


def _completed_project(spark) -> str:
    """Return the first completed project from the generated master CSV."""
    projects = sorted(
        (p for p in load_projects() if p.status == "COMPLETED"),
        key=lambda p: p.project_code,
    )
    if not projects:
        raise RuntimeError("No COMPLETED projects found in sources/master/projects.csv")
    return projects[0].project_code


def _hadoop(*args: str) -> None:
    """Print an HDFS command, run it and fail if it returns an error."""
    print("$ hadoop fs " + " ".join(args), flush=True)
    subprocess.run(["hadoop", "fs", *args], check=True)


def _snapshot_source(spark, project: str, live: dict[str, str]) -> str:
    """The project's folder in the newest raw-zone snapshot that holds it, checked against the live files.

    Raises before anything is deleted when no snapshot holds the folder or the newest one differs from it.
    """
    raw = config.LAKE_RAW
    try:
        names = hdfs.list_snapshots(spark, raw)
    except Py4JJavaError:
        # The raw zone is not snapshottable yet: no collection run has taken a snapshot.
        names = []
    names = sorted((name for name in names if name.startswith(SNAPSHOT_PREFIX)), reverse=True)
    candidates = [name for name in names if hdfs.exists(spark, f"{raw}/.snapshot/{name}/docs/{project}")]
    if not candidates:
        raise RuntimeError(
            f"No snapshot holds {raw}/docs/{project}; run the collection (ingest.run) first. "
            "Nothing was deleted."
        )

    newest = candidates[0]
    source = f"{raw}/.snapshot/{newest}/docs/{project}"
    in_snapshot = _files_with_checksums(spark, source)
    _print_listing(f"SNAPSHOT {newest}", in_snapshot)
    if in_snapshot != live:
        raise RuntimeError(
            f"Snapshot {newest} differs from the live folder ({len(in_snapshot)} vs {len(live)} files); "
            "run the collection (ingest.run) to take a new snapshot. Nothing was deleted."
        )
    print(f"SNAPSHOT {newest} matches the live folder", flush=True)
    return source


def restore(spark, project: str) -> int:
    """Delete the project's raw documents folder and restore it from a snapshot; return the files restored."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project):
        raise ValueError(f"Invalid project code: {project!r}")

    raw = config.LAKE_RAW
    project_dir = f"{raw}/docs/{project}"

    if not hdfs.exists(spark, project_dir):
        raise RuntimeError(f"Project raw folder does not exist: {project_dir}")

    before = _files_with_checksums(spark, project_dir)
    if not before:
        raise RuntimeError(f"No files found in {project_dir}")
    _print_listing(f"BEFORE {project_dir}", before)

    source = _snapshot_source(spark, project, before)

    # The accident: a permanent deletion that bypasses the trash.
    _hadoop("-rm", "-r", "-skipTrash", project_dir)
    if hdfs.exists(spark, project_dir):
        raise RuntimeError(f"{project_dir} still exists after deletion")
    print(f"DELETED: {project_dir} exists = False", flush=True)

    try:
        _hadoop("-cp", source, project_dir)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Copy failed; the files are still in {source}") from exc

    after = _files_with_checksums(spark, project_dir)
    _print_listing(f"AFTER {project_dir}", after)
    if after != before:
        raise RuntimeError(f"Checksum mismatch: before={len(before)}, after={len(after)}")

    print(f"RESTORED {len(after)} files, checksums match", flush=True)
    return len(after)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="project code (default: first COMPLETED project)")
    args = parser.parse_args(argv)

    spark = get_spark("restore-demo")
    try:
        project = args.project or _completed_project(spark)
        print(f"Project: {project}", flush=True)
        restore(spark, project)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
