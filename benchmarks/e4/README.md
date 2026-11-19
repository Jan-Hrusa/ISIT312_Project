# Experiment E4 — File Arrival Rates

## 1. Objective

E4 measures how frequently files arrive in the company's data lake and evaluates whether the current workload requires streaming or can be handled through scheduled batch processing.

The experiment uses the collected-file log (`fve_clean.ingest_log`) and the `business_date` field to measure file arrivals.

The analysis covers **1 January 2016 to 31 October 2026**.

E4 is an arrival-rate analysis. It does not implement or benchmark a streaming pipeline.

## 2. Architecture

The experiment follows this flow:

```text
Raw Zone
   |
   v
File Collection
   |
   v
fve_clean.ingest_log
   |
   v
arrival_rates.sql
   |
   +----------------------+
   |                      |
   v                      v
Monthly Arrivals     Daily Arrivals
   |                      |
   +----------+-----------+
              |
              v
         run_e4.py
              |
              v
          results.csv
              |
              v
       Arrival Analysis
```

The SQL queries aggregate collected files by source and month, and by source and day.

The Python runner uses `common.spark.get_spark()` to execute the queries and generate the CSV results.

## 3. Methodology

Two queries are used:

### Monthly arrivals

For each source and month, the experiment calculates:

- Number of collected files.
- Total file size in bytes.
- Total file size in decimal megabytes (MB).

### Daily arrivals

For each source and day, the experiment calculates the number of arriving files.

The Python runner then calculates:

- Peak daily file arrivals and the corresponding date.
- Median daily file arrivals.
- Number and percentage of calendar days with no new files.

Days with zero arrivals are included in the daily calculations. This avoids calculating the median and no-file percentage using only days when files arrived.

Daily statistics are source-level measurements repeated on each monthly row in `results.csv`.

## 4. Results

The experiment generated **1,560 monthly records**, covering 12 sources across 130 months.

### Arrival summary by source

| Source | Total files | Total size (MB) | Peak files/day | Median files/day | Days with no files |
|---|---:|---:|---:|---:|---:|
| accounting | 559 | 0.62 | 1 | 0 | 85.9% |
| bank_gpc | 4,217 | 1.13 | 3 | 1 | 0.0% |
| bank_sta | 130 | 0.09 | 1 | 0 | 96.7% |
| bank_txt | 4,347 | 0.22 | 4 | 1 | 0.0% |
| budgets | 83 | 0.43 | 1 | 0 | 97.9% |
| docs | 569 | 13.40 | 3 | 0 | 86.7% |
| invoice_pdf | 4,674 | 15.14 | 8 | 1 | 36.5% |
| isdoc | 4,207 | 16.29 | 8 | 1 | 39.9% |
| kpc | 2,058 | 0.58 | 4 | 0 | 74.1% |
| master | 2 | 0.02 | 2 | 0 | 100.0% |
| photos | 30,876 | 237.36 | 73 | 4 | 45.5% |
| video | 333 | 8.19 | 3 | 0 | 92.1% |

### Bank statement comparison

The synthetic dataset contains:

- 4,217 `bank_gpc` files.
- 130 `bank_sta` files.
- 4,347 `bank_txt` companion files.

The `bank_txt` files are companions to bank statements and must not be counted as additional statements.

The two bank statement sources therefore contain 4,347 statement files across 130 months, averaging approximately **33.4 statement files per month**.

The company representative reported approximately **80 bank statement files per month** across the company's four banks.

The synthetic dataset therefore represents a lower bank-statement arrival volume than the reported company workload.

## 5. Batch Processing vs Streaming

The measured arrivals indicate that most company data consists of files arriving periodically rather than a continuous stream of events.

Examples include:

- Bank statements arriving daily or monthly, depending on the bank.
- Invoices arriving as business transactions occur.
- Documents and budgets arriving when they are created or updated.
- Photos and videos arriving in bursts during project activity.

The company currently reviews its cost-versus-budget information periodically rather than requiring second-by-second updates. Its spreadsheet is updated approximately every two to three months.

A scheduled batch process can collect and process the incoming files together, for example through one nightly job. This avoids maintaining a continuously running streaming infrastructure when the current business workload does not require second-level latency.

### Conclusion

Based on the measured file arrival patterns and current reporting requirements, scheduled batch processing is a suitable approach for the existing file-based workload.

Streaming would introduce additional operational complexity without a clear business benefit for these existing file sources.

## 6. Where Streaming Would Fit

Streaming could become valuable for the company's separate plant-monitoring service.

Plant monitoring operates continuously and involves readings from inverters. The representative briefly confirmed a possible monitoring interval of approximately one to five minutes.

For an illustrative estimate, assume:

- 10 plants.
- 20 inverters per plant.
- One reading per minute per inverter.
- Approximately 200 bytes per reading.

Estimated volume:

| Metric | Estimate |
|---|---:|
| Readings per day | 288,000 |
| Data per day | 57.6 MB |
| Readings per year | 105,120,000 |
| Data per year | 21.024 GB |

These are illustrative estimates based on the assumptions above, not measured production monitoring data.

Unlike the existing file-based workload, plant monitoring may benefit from near-real-time processing for alerts and operational monitoring.

## 7. Proposed Streaming Architecture (Not Implemented)

A possible future streaming architecture is:

```text
Plant Inverters
      |
      v
Inverter Monitoring Portals
      |
      v
Kafka Topic
plant-readings
      |
      v
Spark Structured Streaming
      |
      +----------------------+
      |                      |
      v                      v
1-Minute Windows        Alert Processing
      |                      |
      v                      v
Raw Zone              Monitoring Alerts
      |
      v
Existing Data Lake Zones
```

The existing data lake zones could receive the processed monitoring data. Kafka would act as the event ingestion layer, while Spark Structured Streaming would process incoming readings and support window-based calculations.

This is a proposed design only. No Kafka topic, streaming