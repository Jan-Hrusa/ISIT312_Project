"""Experiment E1: the same bank job three ways on the course tools, timed (Task 23.1).

The question: transactions and their sum (CZK) per account and month, from the 075 records of every GPC
statement.

- A `gpc_mrjob.py`: MRJob, `-r hadoop` on YARN;
- B `gpc_spark.py`: Spark on YARN with Task 16's parser;
- C `gpc_hive.sql`: HiveQL compiled to MapReduce on YARN, sent through pyhive.

The GPC files are copied once (`hdfs dfs -put`, no ingest log) to one folder, so all three read the same
input: x10 every .gpc of `sources_x10/` except the planted broken file -> `/bench/x10/e1/gpc/`; scale-1 test
run the first 30 valid files -> `/bench/e1_test/gpc/`. Each version runs `--runs` times (default 3), in turns
A, B, C; the wall time of each run goes to the results file, each version's last output to
`<out>/e1/<version>.tsv`, and the outputs are compared (any difference fails the experiment).

    python -m benchmarks.e1.run_e1                    # scale-1 test run (30 files) -> results_main.csv
    FVE_DATASET=x10 python -m benchmarks.e1.run_e1    # the experiment -> results.csv and the README table
    python -m benchmarks.e1.run_e1 --summary          # README table from results.csv again

Run in the client container with the core and yarn profiles up and the stack otherwise idle.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path

from benchmarks.e1 import compare_outputs
from common import config

HERE = Path(__file__).resolve().parent
README = HERE / "README.md"
COLUMNS = ("version", "run", "seconds", "input_files", "input_mb", "output_rows", "loc")
VERSIONS = ("mrjob", "spark", "hive")
FILES = {"mrjob": "gpc_mrjob.py", "spark": "gpc_spark.py", "hive": "gpc_hive.sql"}
LABELS = {"mrjob": "A MapReduce (mrjob)", "spark": "B Spark", "hive": "C Hive (MapReduce)"}
TEST_FILES = 30
BEGIN, END = "<!-- results:begin -->", "<!-- results:end -->"


def input_dir(dataset: str) -> str:
    return "/bench/x10/e1/gpc" if dataset == "x10" else "/bench/e1_test/gpc"


def results_path(dataset: str) -> Path:
    return HERE / ("results.csv" if dataset == "x10" else f"results_{dataset}.csv")


def gpc_files(sources: Path) -> list[Path]:
    return sorted((sources / "mailbox" / "bank").glob("*/*.gpc"))


def broken_files(files: list[Path], planted_csv: Path) -> set[Path]:
    """The planted BAD_FILE statements: the file of the bank whose 074 statement date is the planted
    transaction's date (`tx_or_order_ref` = <bank>-<yyyyMMdd>-<line>)."""
    if not planted_csv.exists():
        return set()
    with planted_csv.open(encoding="utf-8", newline="") as f:
        refs = [row["tx_or_order_ref"] for row in csv.DictReader(f) if row["problem"] == "BAD_FILE"]
    broken = set()
    for ref in refs:
        bank, day = ref.split("-")[:2]
        ddmmyy = datetime.strptime(day, "%Y%m%d").strftime("%d%m%y")
        broken |= {p for p in files if p.parent.name == bank and _statement_date(p) == ddmmyy}
    return broken


def _statement_date(path: Path) -> str:
    with path.open("rb") as f:
        return f.read(128)[108:114].decode("ascii", "replace")


def input_files(dataset: str) -> list[Path]:
    sources, out = config.dataset_dirs(dataset)
    files = gpc_files(sources)
    if not files:
        raise SystemExit(f"no GPC files in {sources}: generate the {dataset} dataset first")
    broken = broken_files(files, out / "ledger" / "planted_payments.csv")
    valid = [p for p in files if p not in broken]
    return valid if dataset == "x10" else valid[:TEST_FILES]


def lines_of_code(path: Path) -> int:
    """Non-blank, non-comment lines (`#` in Python, `--` in SQL)."""
    marker = "--" if path.suffix == ".sql" else "#"
    return sum(
        1
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith(marker)
    )


def hdfs(*args: str) -> str:
    return subprocess.run(["hdfs", *args], check=True, capture_output=True, text=True).stdout


def check_deletable(path: str) -> None:
    """Deleting is allowed below /bench/ only."""
    if not path.startswith("/bench/") or ".." in path or path.rstrip("/") == "/bench":
        raise ValueError(f"refusing to delete {path!r}: E1 deletes only below /bench/")


def delete(path: str) -> None:
    check_deletable(path)
    subprocess.run(["hdfs", "dfs", "-rm", "-r", "-f", "-skipTrash", path], check=True, capture_output=True)


def prepare(files: list[Path], target: str) -> None:
    """Copy the input once: kept when the folder already holds exactly these files."""
    names = {p.name for p in files}
    listing = subprocess.run(["hdfs", "dfs", "-ls", "-C", target], capture_output=True, text=True)
    if listing.returncode == 0 and {line.rsplit("/", 1)[-1] for line in listing.stdout.split()} == names:
        return
    delete(target)
    hdfs("dfs", "-mkdir", "-p", target)
    for start in range(0, len(files), 500):
        hdfs("dfs", "-put", "-t", "8", *[str(p) for p in files[start : start + 500]], f"{target}/")


def run_mrjob(input_path: str) -> list[tuple]:
    from benchmarks.e1.gpc_mrjob import GpcMonthly

    output = f"{input_path.rsplit('/', 1)[0]}/out_mrjob"
    delete(output)
    job = GpcMonthly(args=["-r", "hadoop", f"hdfs://{input_path}", "--output-dir", f"hdfs://{output}"])
    with job.make_runner() as runner:
        runner.run()
        return [tuple(value) for _, value in job.parse_output(runner.cat_output())]


def run_spark(input_path: str) -> list[tuple]:
    from benchmarks.e1 import gpc_spark

    return gpc_spark.run(input_path)


def run_hive(input_path: str) -> list[tuple]:
    from pyhive import hive

    from warehouse.sql import render

    statements = render(HERE / FILES["hive"], E1_LOCATION=input_path)
    connection = hive.Connection(host=config.HIVE_HOST, port=config.HIVE_PORT, username="hive")
    try:
        cursor = connection.cursor()
        for statement in statements[:-1]:
            cursor.execute(statement)
        cursor.execute(statements[-1])
        return cursor.fetchall()
    finally:
        connection.close()


RUNNERS = {"mrjob": run_mrjob, "spark": run_spark, "hive": run_hive}


def summary(rows: list[dict]) -> str:
    """The README table: median, min and max seconds per version, and the code size."""
    lines = [
        "| Version | Median (s) | Min (s) | Max (s) | Runs | Lines of code | Output rows |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for version in VERSIONS:
        runs = [r for r in rows if r["version"] == version]
        if not runs:
            continue
        seconds = [float(r["seconds"]) for r in runs]
        lines.append(
            f"| {LABELS[version]} | {statistics.median(seconds):.1f} | {min(seconds):.1f} "
            f"| {max(seconds):.1f} | {len(runs)} | {runs[0]['loc']} | {int(runs[0]['output_rows']):,} |"
        )
    first = rows[0]
    lines += [
        "",
        f"Input: {int(first['input_files']):,} GPC files, {float(first['input_mb']):.1f} MB. "
        "Wall time per run, including job submission; raw values in [results.csv](results.csv).",
    ]
    return "\n".join(lines)


def write_readme_table(rows: list[dict]) -> None:
    text = README.read_text(encoding="utf-8")
    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    README.write_text(f"{head}{BEGIN}\n{summary(rows)}\n{END}{tail}", encoding="utf-8")


def read_results(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--versions", nargs="+", choices=VERSIONS, default=list(VERSIONS))
    parser.add_argument("--summary", action="store_true", help="rebuild the README table from results.csv")
    args = parser.parse_args(argv)

    dataset = config.DATASET
    if args.summary:
        write_readme_table(read_results(results_path("x10")))
        return 0

    files = input_files(dataset)
    target = input_dir(dataset)
    prepare(files, target)
    input_mb = sum(p.stat().st_size for p in files) / 1e6
    print(f"E1 on {dataset}: {len(files)} GPC files, {input_mb:.2f} MB in {target}")

    rows, outputs = [], {}
    for run in range(1, args.runs + 1):
        for version in args.versions:
            start = time.perf_counter()
            output = RUNNERS[version](target)
            seconds = time.perf_counter() - start
            outputs[version] = output
            compare_outputs.write_output(compare_outputs.output_dir() / f"{version}.tsv", output)
            rows.append(
                {
                    "version": version,
                    "run": run,
                    "seconds": f"{seconds:.2f}",
                    "input_files": len(files),
                    "input_mb": f"{input_mb:.2f}",
                    "output_rows": len(output),
                    "loc": lines_of_code(HERE / FILES[version]),
                }
            )
            print(f"run {run} {version}: {seconds:.1f} s, {len(output)} rows")

    with results_path(dataset).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    if dataset == "x10":
        write_readme_table(rows)
    print(summary(rows))

    problems = compare_outputs.compare(outputs) if len(outputs) > 1 else []
    for problem in problems:
        print(problem)
    if not problems:
        print(f"outputs identical: {', '.join(outputs)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
