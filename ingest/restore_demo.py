"""Demonstrate restoring a project's raw documents from an HDFS snapshot."""

from __future__ import annotations

import argparse
import re
import subprocess

from common import config, hdfs
from common.spark import get_spark
from common.projects import load_projects


def _files_with_checksums(spark, root: str) -> dict[str, str]:
    """Recursively list files and their HDFS checksums."""
    fs, root_path = hdfs._resolve(spark, root)
    results = {}

    def visit(path):
        for status in fs.listStatus(path):
            child = status.getPath()
            if status.isDirectory():
                visit(child)
            else:
                checksum = fs.getFileChecksum(child)
                relative = child.toString()[len(root.rstrip("/")):]
                results[relative] = str(checksum)

    if fs.exists(root_path):
        visit(root_path)

    return dict(sorted(results.items()))


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
    """Run an HDFS command and fail if it returns an error."""
    subprocess.run(["hadoop", "fs", *args], check=True)


def restore(spark, project: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", project):
        raise ValueError(f"Invalid project code: {project!r}")

    raw = config.LAKE_RAW
    project_dir = f"{raw}/docs/{project}"

    if not hdfs.exists(spark, project_dir):
        raise RuntimeError(f"Project raw folder does not exist: {project_dir}")

    before = _files_with_checksums(spark, project_dir)
    if not before:
        raise RuntimeError(f"No files found in {project_dir}")

    print(f"BEFORE: {len(before)} files")

    # Demonstrate the accidental permanent deletion.
    _hadoop("-rm", "-r", "-skipTrash", project_dir)

    after_delete = _files_with_checksums(spark, project_dir)
    if after_delete:
        raise RuntimeError("Project files still exist after deletion")

    print("DELETED: project raw folder is empty")

    # Find the newest snapshot containing this project's documents.
    snapshots = hdfs.list_snapshots(spark, raw)
    candidates = [
        name for name in snapshots
        if name.startswith("raw-")
        and hdfs.exists(spark, f"{raw}/.snapshot/{name}/docs/{project}")
    ]

    if not candidates:
        raise RuntimeError(f"No snapshot contains documents for {project}")

    newest = max(candidates)
    source = f"{raw}/.snapshot/{newest}/docs/{project}"

    print(f"RESTORING FROM: {newest}")

    _hadoop("-cp", source, project_dir)

    after_restore = _files_with_checksums(spark, project_dir)

    if before != after_restore:
        raise RuntimeError(
            f"Checksum mismatch: before={len(before)}, after={len(after_restore)}"
        )

    print(f"RESTORED {len(after_restore)} files, checksums match")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="project code (default: first COMPLETED project)")
    args = parser.parse_args(argv)

    spark = get_spark("restore-demo")
    try:
        project = args.project or _completed_project(spark)
        print(f"Project: {project}")
        restore(spark, project)
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
