# Experiment E5 — Hive MapReduce vs Spark SQL

## Objective

Compare the performance of five dashboard queries using Hive MapReduce on YARN and Spark SQL on the 10× warehouse.

## Queries

- Q1: Budget vs Actual
- Q3: Cumulative Spend
- Q4: Overrun Rank
- Q5: Cost per MWp
- V1: Project List

## Methodology

Each query is executed three times per engine.

- Run 1: Cold attempt
- Runs 2–3: Warm attempts
- Timing includes SQL execution and fetching all result rows.
- Results are recorded in results.csv.

Before performance comparison, verify that both engines return equivalent results on the main dataset.

## Run commands

From the project root:

Hive MapReduce:

    docker compose -f docker/docker-compose.yml exec client python -m benchmarks.e5.run_e5 --engine hive

Spark SQL:

    docker compose -f docker/docker-compose.yml exec client python -m benchmarks.e5.run_e5 --engine spark

Both commands default to database fve_dw_x10.

## Partitioning experiment

The file partition_test.sql compares:

- Partitioned fact_invoice_line
- Unpartitioned fact_invoice_line_flat

Both queries filter on issue_year = 2025.

Compare execution times and EXPLAIN EXTENDED plans to evaluate partition pruning.

## Results

The following averages are calculated from three executions per query and engine.

| Query | Hive average (s) | Spark average (s) | Spark speedup |
|---|---:|---:|---:|
| Q1 | 560.314 | 15.865 | 35.32x |
| Q3 | 148.796 | 4.457 | 33.39x |
| Q4 | 283.316 | 7.388 | 38.35x |
| Q5 | 172.740 | 3.338 | 51.74x |
| V1 | 440.078 | 7.122 | 61.79x |

All five queries produced matching row counts and SHA-256 fingerprints across Hive and Spark.

For the partitioning experiment, both engines returned 11,759 invoice lines
and a total net amount of 2,087,597,535.64 for issue_year = 2025.

| Engine | Partitioned (s) | Unpartitioned (s) |
|---|---:|---:|
| Hive MapReduce | 58.454 | 58.630 |
| Spark SQL | 1.057 | 0.555 |

Partitioning timings represent one execution per configuration.

## Interpretation

Spark SQL outperformed Hive MapReduce across all five dashboard queries,
with measured speedups ranging from 33.39x to 61.79x. These results suggest
that Spark SQL is better suited to the interactive dashboard workload
under the tested configuration.

Hive MapReduce incurred substantially higher execution times, consistent
with the overhead of launching and coordinating MapReduce jobs. Spark SQL
can execute these analytical queries more efficiently through its execution
engine, although the benchmark does not isolate individual sources of overhead.

Hive EXPLAIN showed the partition-specific HDFS path for issue_year = 2025.
Spark EXPLAIN showed PartitionFilters for the same year, confirming that
partition pruning was applied by both engines.

However, the measured partitioned queries were not consistently faster
than the unpartitioned queries. Because each configuration was timed only
once, these measurements are insufficient to establish a reliable
performance benefit from partitioning.

The findings apply to the tested 10x warehouse, query workload, and
execution environment rather than all possible Hive and Spark deployments.

## Result validation

After running both engines, compare row counts and SHA256 fingerprints:

    docker compose -f docker/docker-compose.yml exec client python benchmarks/e5/compare_results.py

The comparison script checks all five queries and reports PASS, FAIL, or INCOMPLETE.

A fingerprint mismatch requires investigation because Hive and Spark may represent equivalent numeric values differently.

## Benchmark limitations

- Run 1 is treated as a cold attempt; caches are not explicitly cleared.
- Runs 2 and 3 are warm attempts.
- Timing includes query execution and retrieval of all result rows.
- Hive is configured to use MapReduce on YARN.
- Engine execution must be verified using YARN and Spark monitoring interfaces.
- Performance conclusions must be based on measured results, not assumptions.

## Evidence checklist

- Hive MapReduce execution and YARN application evidence
- Spark SQL execution evidence
- Completed results.csv
- Cross-engine result comparison
- Partitioned and unpartitioned query timings
- EXPLAIN EXTENDED output showing partition-pruning behavior
- Final interpretation of measured performance differences
