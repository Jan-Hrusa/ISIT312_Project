"""Experiment E2: HDFS's small-files problem and the daily SequenceFiles that fix it (Task 24.1).

Two ways to store the same photos, `--runs` times each (default 3):

- loose:  `hdfs dfs -put` of the photo folder into `<bench>/loose/`: one HDFS file (and block) per photo;
- packed: the collection job with Task 18's packer, `ingest.collect.collect(spark, sources=["photos"])`:
          one SequenceFile per day under `<lake>/raw/photos/`.

After each variant: the folder's files, directories and blocks (`hdfs dfs -count`, `hdfs fsck`), the
NameNode heap (JMX MemHeapUsedM), the write time, and the time to read `--read` random photos back
(loose: one file each; packed: the day's SequenceFile and key from ingest_log, `read_seq` + filter). Every
photo read back is compared with its source file. Before each variant its folder is cleared, and for
packed also the lake root and the ingest_log table: the only place in the project where deleting is
allowed, and only below `/bench/`.

    FVE_DATASET=x10 python -m benchmarks.e2.run_e2            # the experiment: 291,840 photos -> results.csv
    python -m benchmarks.e2.run_e2                            # scale-1 dry run -> results_main.csv
    python -m benchmarks.e2.run_e2 --summary                  # README table from results.csv again

x10 uses the x10 settings (`sources_x10/`, `/bench/x10/lake`, `fve_clean_x10`); the scale-1 dry run is
redirected to `/bench/main/lake` and the database `fve_bench_main`, so `/lake` and `fve_clean` are never
touched. Run in the client container with the core profile up; `--pause` waits before and after each
variant of run 1 for the NameNode UI screenshots.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import statistics
import time
from pathlib import Path

from benchmarks.e2 import namenode_stats as nn
from common import config, hdfs

HERE = Path(__file__).resolve().parent
README = HERE / "README.md"
COLUMNS = ("variant", "run", "files", "blocks", "dirs", "heap_mb", "seconds", "read_100_seconds")
VARIANTS = ("loose", "packed")
BEGIN, END = "<!-- results:begin -->", "<!-- results:end -->"


def results_path(dataset: str) -> Path:
    return HERE / ("results.csv" if dataset == "x10" else f"results_{dataset}.csv")


def bench_root(dataset: str) -> str:
    return f"/bench/{dataset}"


def use_bench_lake(dataset: str) -> None:
    """Point the lake and the clean database at the experiment's own place for the scale-1 dry run
    (x10 already has them: `/bench/x10/lake`, `fve_clean_x10`)."""
    if dataset == "x10":
        return
    root = f"{bench_root(dataset)}/lake"
    config.LAKE_ROOT, config.LAKE_RAW = root, f"{root}/raw"
    config.LAKE_CLEAN, config.LAKE_DW = f"{root}/clean", f"{root}/dw"
    config.CLEAN_DB = f"fve_bench_{dataset}"


def check_deletable(path: str) -> None:
    """Deleting is allowed below /bench/ only."""
    if not path.startswith("/bench/") or ".." in path or path.rstrip("/") == "/bench":
        raise ValueError(f"refusing to delete {path!r}: E2 deletes only below /bench/")


def delete(spark, path: str) -> None:
    check_deletable(path)
    jvm = spark.sparkContext._jvm
    target = jvm.org.apache.hadoop.fs.Path(path)
    file_system = target.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
    if file_system.exists(target):
        file_system.delete(target, True)


def clear(spark, variant: str, dataset: str) -> None:
    if variant == "loose":
        delete(spark, f"{bench_root(dataset)}/loose")
    else:
        delete(spark, config.LAKE_ROOT)
        spark.sql(f"DROP TABLE IF EXISTS {config.CLEAN_DB}.ingest_log")


def photo_files(dataset: str) -> list[Path]:
    folder = Path(config.SOURCES_DIR) / config.RAW_SOURCES["photos"].folder
    files = sorted(p for p in folder.glob("*.jpg") if not p.name.startswith("."))
    if not files:
        raise SystemExit(f"no photos in {folder}: generate the {dataset} dataset first")
    return files


def write_loose(local_folder: Path, dataset: str, threads: int) -> float:
    target = f"{bench_root(dataset)}/loose"
    nn.run_hdfs("dfs", "-mkdir", "-p", target)
    put = ["dfs", "-put"] + (["-t", str(threads)] if threads > 1 else []) + [str(local_folder), f"{target}/"]
    t0 = time.perf_counter()
    nn.run_hdfs(*put)
    return time.perf_counter() - t0


def write_packed(spark) -> float:
    from ingest.collect import collect

    t0 = time.perf_counter()
    collect(spark, sources=["photos"])
    return time.perf_counter() - t0


def variant_dir(variant: str, dataset: str) -> str:
    return f"{bench_root(dataset)}/loose" if variant == "loose" else f"{config.LAKE_RAW}/photos"


def read_loose(spark, names: list[str], dataset: str) -> tuple[float, dict[str, bytes]]:
    folder = f"{bench_root(dataset)}/loose/{config.RAW_SOURCES['photos'].folder.rsplit('/', 1)[-1]}"
    t0 = time.perf_counter()
    data = {name: hdfs.read_bytes(spark, f"{folder}/{name}") for name in names}
    return time.perf_counter() - t0, data


def read_packed(spark, names: list[str]) -> tuple[float, dict[str, bytes]]:
    from pyspark.sql import functions as F

    from ingest.seqfile import read_seq

    t0 = time.perf_counter()
    rows = (
        spark.table(f"{config.CLEAN_DB}.ingest_log")
        .where((F.col("source") == "photos") & F.col("seq_key").isin(names))
        .select("raw_path", "seq_key")
        .collect()
    )
    where = {row.seq_key: row.raw_path for row in rows}
    data = {}
    for name in names:
        record = read_seq(spark, where[name]).filter(lambda kv, key=name: kv[0] == key).first()
        data[name] = record[1]
    return time.perf_counter() - t0, data


def check_read_back(data: dict[str, bytes], local: dict[str, Path]) -> None:
    for name, got in data.items():
        if hashlib.sha256(got).digest() != hashlib.sha256(local[name].read_bytes()).digest():
            raise RuntimeError(f"{name} read back from HDFS differs from its source file")


def pause(message: str, enabled: bool) -> None:
    if enabled:
        input(f"\n>>> {message} – take the NameNode UI screenshot (http://localhost:9870), then press Enter ")


def run(runs: int, read: int, threads: int, seed: int, screenshots: bool) -> list[dict]:
    from common.spark import get_spark

    dataset = config.DATASET
    use_bench_lake(dataset)
    files = photo_files(dataset)
    local = {p.name: p for p in files}
    print(f"E2 on the {dataset} dataset: {len(files):,} photos in {files[0].parent}")
    spark = get_spark("e2")
    rows = []
    for run_no in range(1, runs + 1):
        sample = random.Random(seed + run_no).sample(sorted(local), min(read, len(local)))
        for variant in VARIANTS:
            clear(spark, variant, dataset)
            before = nn.jmx()
            pause(f"run {run_no}, before {variant}", screenshots and run_no == 1)
            if variant == "loose":
                seconds = write_loose(files[0].parent, dataset, threads)
                read_seconds, data = read_loose(spark, sample, dataset)
            else:
                seconds = write_packed(spark)
                read_seconds, data = read_packed(spark, sample)
            check_read_back(data, local)
            stats = nn.dir_stats(variant_dir(variant, dataset))
            after = nn.jmx()
            pause(f"run {run_no}, after {variant}", screenshots and run_no == 1)
            objects_before = before["files_total"] + before["blocks_total"]
            objects_after = after["files_total"] + after["blocks_total"]
            row = {
                "variant": variant,
                "run": run_no,
                "files": stats["files"],
                "blocks": stats["blocks"],
                "dirs": stats["dirs"],
                "heap_mb": round(after["heap_mb"], 1),
                "seconds": round(seconds, 2),
                "read_100_seconds": round(read_seconds, 3),
            }
            rows.append(row)
            print(
                f"run {run_no} {variant:6s}: {stats['files']:,} files, {stats['blocks']:,} blocks, "
                f"{stats['dirs']:,} dirs ({stats['bytes'] / 1e6:,.1f} MB), write {seconds:.1f} s, "
                f"read {len(sample)} in {read_seconds:.2f} s, heap {before['heap_mb']:.0f} -> "
                f"{after['heap_mb']:.0f} MB, NameNode objects {objects_before:,} -> {objects_after:,}"
            )
    write_results(rows, results_path(dataset))
    return rows


def write_results(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(HERE.parents[1])}")


def read_results(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def summarize(rows: list[dict]) -> dict[str, dict]:
    """Per variant: objects (files + dirs + blocks, the same in every run), their rule-of-thumb memory and
    the medians of heap, write time and read time."""
    out = {}
    for variant in VARIANTS:
        mine = [r for r in rows if r["variant"] == variant]
        if not mine:
            continue
        stats = {k: int(mine[-1][k]) for k in ("files", "dirs", "blocks")}
        out[variant] = {
            **stats,
            "runs": len(mine),
            "objects": nn.objects(stats),
            "estimated_mb": nn.estimated_mb(stats),
            "heap_mb": statistics.median(float(r["heap_mb"]) for r in mine),
            "seconds": statistics.median(float(r["seconds"]) for r in mine),
            "read_seconds": statistics.median(float(r["read_100_seconds"]) for r in mine),
        }
    return out


def results_table(summary: dict[str, dict]) -> str:
    lines = [
        "| Variant | Files | Dirs | Blocks | Objects | ~150 B/object | NameNode heap after | Write"
        " | Read 100 random |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, s in summary.items():
        lines.append(
            f"| {variant} | {s['files']:,} | {s['dirs']:,} | {s['blocks']:,} | {s['objects']:,} | "
            f"{s['estimated_mb']:.1f} MB | {s['heap_mb']:.0f} MB | {s['seconds']:.0f} s | "
            f"{s['read_seconds']:.2f} s |"
        )
    if {"loose", "packed"} <= set(summary):
        share = summary["packed"]["objects"] / summary["loose"]["objects"]
        lines += ["", f"Packed objects are {share:.2%} of the loose objects (target: below 2%)."]
    runs = max(s["runs"] for s in summary.values())
    lines += ["", f"Medians of {runs} runs per variant; raw values in [results.csv](results.csv)."]
    return "\n".join(lines)


def update_readme(table: str, readme: Path = README) -> None:
    """Replace the README's results section (between the two markers) with `table`."""
    text = readme.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        raise ValueError(f"{readme.name} has no {BEGIN} ... {END} section")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(f"{head}{BEGIN}\n{table}\n{END}{tail}", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Experiment E2: loose photos vs daily SequenceFiles on HDFS")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--read", type=int, default=100, help="random photos read back per variant and run")
    parser.add_argument("--put-threads", type=int, default=8, help="hdfs dfs -put -t (1 = no -t option)")
    parser.add_argument("--seed", type=int, default=config.SEED)
    parser.add_argument("--pause", action="store_true", help="wait for NameNode UI screenshots in run 1")
    parser.add_argument(
        "--summary", action="store_true", help="only rebuild the README table from results.csv"
    )
    args = parser.parse_args(argv)

    if not args.summary:
        run(args.runs, args.read, args.put_threads, args.seed, args.pause)
    path = results_path(config.DATASET) if not args.summary else HERE / "results.csv"
    summary = summarize(read_results(path))
    table = results_table(summary)
    print("\n" + table)
    if path.name == "results.csv":
        update_readme(table)
        print(f"\n{README.name} updated")


if __name__ == "__main__":
    main()
