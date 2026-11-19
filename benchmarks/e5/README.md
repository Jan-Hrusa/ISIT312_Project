# E5: Hive on MapReduce vs Spark SQL for the dashboard queries

The question: can the management dashboard run on Hive with plain MapReduce, or does it need Spark SQL? The same
five dashboard queries (`warehouse/queries`: q1 budget vs actual, q3 cumulative spend, q4 overrun rank, q5 cost per
MWp, v1 project list) run on the 10x warehouse `fve_dw_x10` on two engines, both through HiveServer2's protocol
(pyhive): **Hive** (HiveServer2 :10000, `mapreduce.framework.name=yarn`, MapReduce on YARN) and **Spark SQL** (the
Spark Thrift Server `sparksql` :10001 that the Zeppelin dashboard uses). A second test compares a year filter on
the partitioned `fact_invoice_line` with an unpartitioned copy.

## Setup
1. The 10x dataset, in the client container with `sources_x10/` and `out_x10/` empty (about 15 GB free disk):
   `python -m generators.scale --scale 10`; it must end with `OK` against `docs/x10-MANIFEST.sha256`
   (`docs/dataset-stats.md`).
2. The 10x warehouse (about 1 hour): `python run_pipeline.py --dataset x10 --steps collect,bank,finance,matching,warehouse`
   gives `fve_dw_x10`.
3. Profiles: Hive needs `docker compose --profile core --profile yarn up -d`, Spark needs `--profile core
   --profile zeppelin` (service `sparksql`). On an 8 GB laptop run one engine, stop its profile, then the other.

## Commands (client container, `docker compose exec client ...`)
    python -m benchmarks.e5.run_e5 --engine hive          # 5 queries x 3 runs -> results.csv
    python -m benchmarks.e5.run_e5 --engine spark
    python -m benchmarks.e5.run_partition --engine hive   # partition test, plans -> explain_*_hive.txt
    python -m benchmarks.e5.run_partition --engine spark
    python -m benchmarks.e5.compare_results               # same rows on both engines? + the table below

Every run opens its own connection and is timed until the last row is fetched; run 1 is the cold run, the warm
value is the median of runs 2-3. Each run's rows get a SHA-256 fingerprint of the sorted rows, so `compare_results`
shows that both engines return the same result. A rerun of one engine replaces only that engine's rows in
`results.csv`. Add `--database fve_dw` to check everything on the main dataset first (under a minute on Spark,
about 20 minutes on Hive; all PASS on 19 Nov).

## Results (10x warehouse, measured 18-19 Nov 2026)
All five queries returned the same rows on both engines in every run (`compare_results`: PASS); raw times in
[results.csv](results.csv).

| Query | Rows | Hive cold (s) | Spark cold (s) | Hive warm (s) | Spark warm (s) | Spark faster (warm) |
|---|---:|---:|---:|---:|---:|---:|
| q1 budget vs actual | 8,900 | 1053.6 | 27.74 | 313.6 | 9.93 | 31.6x |
| q3 cumulative spend | 8,202 | 143.0 | 4.71 | 151.7 | 4.33 | 35.0x |
| q4 overrun rank | 10 | 280.9 | 9.73 | 284.5 | 6.21 | 45.8x |
| q5 cost per MWp | 736 | 166.3 | 3.28 | 176.0 | 3.37 | 52.2x |
| v1 project list | 808 | 435.2 | 10.09 | 442.5 | 5.64 | 78.5x |

Partition test (`partition_test.sql`; 2025 invoice lines: 11,759 lines, net 2,087,597,535.64 on both tables and
engines; one run each in this measurement):

| Engine | Partitioned (s) | Flat copy (s) | What the plan reads |
|---|---:|---:|---|
| Hive (MapReduce on YARN) | 58.45 | 58.63 | only `issue_year=2025`: est. 2.8 MB vs 71.3 MB for the flat copy ([plan](explain_partitioned_hive.txt), [flat](explain_unpartitioned_hive.txt)) |
| Spark SQL | 1.06 | 0.56 | one partition path, `PartitionFilters: issue_year = 2025` ([plan](explain_partitioned_spark.txt)); the flat copy only gets an ORC pushed filter ([flat](explain_unpartitioned_spark.txt)) |

## What it shows
A dashboard click has to answer in a few seconds. Spark SQL does that on the 10x warehouse: 3-10 s per query warm,
at most 28 s cold, while Hive on MapReduce needs 2.5 to 7.5 minutes per query warm and 17.6 minutes for the cold
q1, about 30 to 80 times slower. The reason is how MapReduce runs a query: Hive compiles it into a chain of
MapReduce jobs (on the main dataset q3 became 2, q1 and q5 4, q4 6 and v1 9, HiveServer2 log), and every job is
submitted to YARN, waits for its own ApplicationMaster and container JVMs to start, and writes its whole output to
HDFS before the next job can read it. Spark keeps one application with its executors running and passes data
between stages through memory and its shuffle, so a query pays none of these start-up costs. That fixed cost is
also why Hive's times hardly change between the cold and warm runs (q3-v1 within 7 %); only q1's first run was
three times slower than its others. Partition pruning works in both engines: each reads only the 2025 folder, in
Hive's estimate 2.8 MB of the table's 71.3 MB. At this size the saved reading is far smaller than a MapReduce
job's fixed cost (about 58 s even for this one-row count), so the timing shows no gain; the saving grows with
every year of history the company keeps, while the per-job cost stays. For the company: the dashboard runs on
Spark SQL (as built, through the Thrift Server), and Hive on MapReduce stays for nightly batch work, where minutes
don't matter.

## Limits of the measurement
- Cold = the first run; caches (HDFS, OS, the Thrift Server's) were not cleared, and there are three runs per query.
- One machine (the stack's single 2 GB NodeManager for Hive); on a real cluster both engines get faster, the
  per-job start-up of MapReduce stays.
- The partition times are one run each; `run_partition` now times each query `--runs` times (default 3).
- Hive's plan sizes are statistics estimates (its row estimate for the 2025 partition, 3,719, is stale: the query
  counted 11,759), so read them as proportions, not exact bytes.
- Hive on MapReduce in local mode (the stack's default for HiveServer2) was not measured.

## Files
`run_e5.py` (the five queries), `run_partition.py` + `partition_test.sql` (partition test; the flat copy is dropped
again at the end), `compare_results.py` (checks and the table above), `results.csv` (every run;
`partition_yes` / `partition_no` = the partition test), `partition_results_<engine>.csv` (every statement of the
partition test with its result), `explain_*_<engine>.txt` (EXPLAIN EXTENDED plans).
