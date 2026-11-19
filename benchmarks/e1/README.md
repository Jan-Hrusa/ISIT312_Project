# E1: bank data – MapReduce vs Spark vs Hive

The question for "why Spark and not MapReduce": the same bank job written three ways on the course tools and
timed. The job reads every 075 transaction record of the GPC statements and returns, per account and month, the
number of transactions and their sum in CZK (month = `yyyy-MM` of the record's value date; amounts signed as in
Task 16, debits negative; haléře ÷ 100).

| Version | File | How it runs |
|---|---|---|
| A | [`gpc_mrjob.py`](gpc_mrjob.py) | MRJob (Hadoop streaming), `-r hadoop` on YARN: mapper cuts the fixed positions, combiner and reducer sum |
| B | [`gpc_spark.py`](gpc_spark.py) | Spark on YARN: `binaryFiles` → Task 16's `processing.bank.gpc.parse` → `groupBy(account, month)`; `processing/` and `common/` are zipped and shipped with `addPyFile` |
| C | [`gpc_hive.sql`](gpc_hive.sql) | HiveQL on HiveServer2 (MapReduce on YARN): an EXTERNAL text table over the folder, `substr` on the fixed positions, `GROUP BY`; sent through pyhive |

**Input.** Every `.gpc` of `sources_x10/` except the planted broken statement (the `BAD_FILE` row of
`out_x10/ledger/planted_payments.csv`, found by its statement date) is copied once with `hdfs dfs -put`, no ingest
log, to `/bench/x10/e1/gpc/`, so all three versions read the same valid input: 4,216 files, 6.3 MB.

**Small files.** The statements are a few KB each (RB sends one a day). With Hadoop's default input format,
version A started one map task per file: on the scale-1 test (30 files) it took 63.8 s against 27.7 s with
`CombineTextInputFormat`, and on x10 it would start 4,216 map tasks on a NodeManager that runs three containers at
a time. Version A therefore combines files into splits of up to 256 MB, as Hive does by default
(`CombineHiveInputFormat`) and as Spark's `binaryFiles` does; E1 compares the engines, and E2 the small-files
problem itself.

## How to run

In the client container, with the core and yarn profiles up and nothing else running
(`docker compose --profile core --profile yarn up -d`, then `./check.sh`):

```
python -m generators.scale --scale 10               # once: the x10 dataset (about 15 minutes, must print OK)
python -m benchmarks.e1.run_e1 --runs 1             # scale-1 test: 30 files -> /bench/e1_test/gpc/, results_main.csv
FVE_DATASET=x10 python -m benchmarks.e1.run_e1      # the experiment: 3 runs per version -> results.csv, table below
FVE_DATASET=x10 python -m benchmarks.e1.compare_outputs   # the three outputs again: must print OK
```

`run_e1` runs A, B, C in turns, three times each, and times each run from submission to the last output row
(wall clock, including YARN start-up). Each version's last output goes to `out_x10/e1/<version>.tsv`; the run fails
if the three outputs differ. `python -m benchmarks.e1.run_e1 --summary` rebuilds the table from `results.csv`.
Lines of code are the non-blank, non-comment lines of each version's file. The YARN UI (http://localhost:8088)
shows the MapReduce and Spark applications; screenshots in Drive `Screenshots/benchmarks/`.

## Results (x10 dataset)

<!-- results:begin -->
| Version | Median (s) | Min (s) | Max (s) | Runs | Lines of code | Output rows |
|---|---:|---:|---:|---:|---:|---:|
| A MapReduce (mrjob) | 28.2 | 28.1 | 30.8 | 3 | 36 | 381 |
| B Spark | 53.9 | 50.3 | 55.1 | 3 | 44 | 381 |
| C Hive (MapReduce) | 155.1 | 149.5 | 156.0 | 3 | 22 | 381 |

Input: 4,216 GPC files, 6.3 MB. Wall time per run, including job submission; raw values in [results.csv](results.csv).
<!-- results:end -->

All three outputs were identical in every run (381 account-months; `compare_outputs` prints `OK`).

Where the time goes (one run each, from the job history server and a timed Spark run):

| Version | Start-up | The work | Rest |
|---|---|---|---|
| A MapReduce | YARN job ≈ 2.5 s from submit to start | 1 map task over all 4,216 files: 3.8 s; shuffle 1.1 s, reduce 0.2 s (job ≈ 10 s) | ≈ 18 s in mrjob: packing and submitting the job, reading the output back |
| B Spark | 9.3 s: YARN application and its one executor (512 MB, 1 core) | 1 partition (`binaryFiles` packed the small files together): 41.1 s of Task 16's parser in one Python worker | listing 1.3 s |
| C Hive | ≈ 3 s from submit to start | 1 map task: ≈ 139 s stepping through the 4,216 files; reduce under 1 s | query compile and fetch, a few seconds |

## What it means

At 6.3 MB and 381 output rows no version is limited by the data: each run is start-up plus one task, and which
task is slow decides the order. MapReduce is fastest here because its single map only cuts four fixed fields per
line (3.8 s); its usual cost, writing the map output to disk and shuffling it before the reduce, is about one second
when the output is 381 small rows, and it would grow with every extra stage a longer pipeline chains through disk.
Spark keeps its stages in memory, but that saves little in a one-stage job: its 54 s is a 9 s YARN start-up and
41 s of one Python worker running Task 16's full parser (header totals, every field validated) on one 512 MB,
single-core executor, because the small files fit into one partition; more partitions and cores would spread that
work, the stack's YARN allows one such executor. Hive needs the least code (22 lines of SQL that an analyst can
read and change) and compiles to one MapReduce job, but its single map task spent about 139 s going through the
4,216 small files, against 3.8 s for the streaming map over the same files, so on this input it is the slowest.
For the company's nightly batch, where a day adds a handful of statements, all three finish in minutes; the
pipeline uses Spark because the bank job reuses the tested Task 16 parsers (validation, TXT details, `PARSE_ERROR`
issues) instead of a second copy of the fixed positions, and the same engine runs the finance, matching and media
jobs.
