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

Pending benchmark execution.

## Interpretation

Pending measured results and execution-plan analysis.

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
