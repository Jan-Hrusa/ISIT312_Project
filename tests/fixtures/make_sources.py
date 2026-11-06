"""Build a dated `sources/` tree from the committed test fixtures.

Git doesn't keep file modification times, but the collection job takes each file's business date from its
mtime. Fixture files therefore live in `tests/fixtures/sources/` (same layout as `sources/`) and their dates
in `tests/fixtures/mtimes_<area>.csv`: header `path,business_date`, path relative to `sources/` and
`/`-separated, date `yyyy-MM-dd`. This copies the tree and sets every file's mtime to 12:00 UTC of its
business date, as the generators do.

Usage inside the client container: `python -m tests.fixtures.make_sources <dest folder>`.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent


def business_mtime(day: date) -> float:
    """POSIX timestamp of 12:00 UTC on `day` (the mtime every generator sets)."""
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).timestamp()


def read_mtimes(fixtures_dir: Path = FIXTURES_DIR) -> dict[str, date]:
    """All business dates from `mtimes_*.csv`; a path listed twice is a ValueError."""
    dates: dict[str, date] = {}
    for csv_path in sorted(fixtures_dir.glob("mtimes_*.csv")):
        with csv_path.open(encoding="utf-8", newline="") as f:
            for line_no, row in enumerate(csv.DictReader(f), start=2):
                rel = row["path"].strip().strip("/")
                if rel in dates:
                    raise ValueError(f"{csv_path.name}, line {line_no}: {rel} is listed twice")
                dates[rel] = date.fromisoformat(row["business_date"].strip())
    return dates


def make_sources(dest: Path, fixtures_dir: Path = FIXTURES_DIR) -> Path:
    """Copy `<fixtures_dir>/sources/` to `dest` and set each file's mtime; return `dest`.

    Every fixture file needs a business date and every dated path must exist, otherwise ValueError (a file
    without a date would land in the wrong raw-zone month). Files starting with "." (.gitkeep) are skipped.
    """
    src = fixtures_dir / "sources"
    dates = read_mtimes(fixtures_dir)
    files = (
        sorted(
            p.relative_to(src).as_posix()
            for p in src.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        )
        if src.is_dir()
        else []
    )

    undated = [f for f in files if f not in dates]
    if undated:
        raise ValueError(f"fixture files without a business date in mtimes_*.csv: {', '.join(undated)}")
    unknown = sorted(set(dates) - set(files))
    if unknown:
        raise ValueError(f"mtimes_*.csv lists files that don't exist: {', '.join(unknown)}")

    dest.mkdir(parents=True, exist_ok=True)
    for rel in files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / rel, target)
        ts = business_mtime(dates[rel])
        os.utime(target, (ts, ts))
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dest", type=Path, help="folder to create the dated sources tree in")
    args = parser.parse_args()
    out = make_sources(args.dest)
    print(f"sources tree written to {out}")


if __name__ == "__main__":
    main()
