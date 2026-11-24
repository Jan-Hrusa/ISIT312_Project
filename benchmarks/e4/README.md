# Experiment E4: file arrival rates (batch, not streaming)

## 1. Objective
E4 measures how often and how much data reaches the data lake per source, and from that whether the company needs
streaming or whether a scheduled batch run is enough. It argues from measured arrival rates; it does not build or
benchmark a streaming pipeline. Streaming (Kafka, Spark Streaming) is not built in this project (project decision of
3 Nov 2026); section 7 is a design sketch only.

Data: the collected-file log `fve_clean.ingest_log` of the main (scale-1) dataset, one row per collected file (each
photo of a daily SequenceFile is its own row), counted by its `business_date`, from 1 January 2016 to 31 October 2026
(3,957 days, 130 months).

## 2. How it works
```text
sources/ (mailbox, Money S3 export, Drive, phones)
   |  collection job (Task 14): copies every new file into the raw zone, one ingest_log row per file
   v
/lake/raw  +  fve_clean.ingest_log (source, business_date, size_bytes, ...)
   |
   v
arrival_rates.sql (runs on Spark SQL and on Hive)
   monthly_arrivals: files and bytes per source and month
   daily_arrivals:   files per source and day
   source_totals:    files, MB and days with files per source
   |
   v
run_e4.py -> results.csv (per source and month), summary.csv (per source and all sources)
```

Run in the client container (profile `core`, after the collect step): `python -m benchmarks.e4.run_e4` (about 1
minute). Days without a file count as 0 in the daily statistics, so the median and the share of empty days use every
calendar day, not only the days on which files arrived. `run_e4` also checks its per-source totals against
`source_totals`.

## 3. Results
`results.csv`: 1,560 rows (12 sources x 130 months; months without a file are 0). `summary.csv`, from the run on
the team lead's desktop stack on 19 Nov 2026 (the same numbers as Ryan's run):

| Source | Files | MB | Files per day | Peak day (files) | Median day | Days with no file |
|---|---:|---:|---:|---:|---:|---:|
| accounting (Money S3 export) | 559 | 0.62 | 0.14 | 1 | 0 | 85.9 % |
| bank_gpc (statements) | 4,217 | 1.13 | 1.07 | 3 | 1 | 0.0 % |
| bank_sta (statements) | 130 | 0.09 | 0.03 | 1 | 0 | 96.7 % |
| bank_txt (statement companions) | 4,347 | 0.22 | 1.10 | 4 | 1 | 0.0 % |
| budgets | 83 | 0.43 | 0.02 | 1 | 0 | 97.9 % |
| docs | 569 | 13.40 | 0.14 | 3 | 0 | 86.7 % |
| invoice_pdf | 4,674 | 15.14 | 1.18 | 8 | 1 | 36.5 % |
| isdoc | 4,207 | 16.29 | 1.06 | 8 | 1 | 39.9 % |
| kpc (payment orders) | 2,058 | 0.58 | 0.52 | 4 | 0 | 74.1 % |
| master | 2 | 0.02 | 0.00 | 2 | 0 | 100.0 % (all on the last day) |
| photos | 30,876 | 237.36 | 7.80 | 73 | 4 | 45.5 % |
| video | 333 | 8.19 | 0.08 | 3 | 0 | 92.1 % |
| **all sources** | **52,055** | **293.46** | **13.16** | **85** | **10** | **0.0 %** |

Bank statements: 4,217 GPC + 130 STA = 4,347 statement files in 130 months, about 33.4 a month (the TXT files are
companions of these statements, not extra statements). The company's representative estimated about 80 statement
files a month across its four banks, one bank sending one every day. The demo generates fewer; at 80 a month the
total arrival grows by about 1.5 files a day, which changes nothing below.

## 4. What the numbers show
The data arrives as files, a few at a time: on a typical day 10 files of all sources together (median), 13 on
average, at most 85 on the busiest day (a burst of site photos), together about 0.07 MB a day. Photos are the only
source with bursts, up to 73 on one day; everything else arrives at most 8 files a day, and accounting exports,
budgets, documents and videos arrive on fewer than one day in six.

## 5. Batch, not streaming
Kafka and Spark Streaming (course Weeks 8 and 9) are built for continuous streams of events processed within
seconds. This company produces about 13 files a day, and nobody needs them faster than the next morning: the cost
overview is designed to be read once a day, and in the call-back the company confirmed that an update during the night is enough
(Company representative, 8 Nov 2026; today the spreadsheet is updated by hand only every 2-3 months). One nightly
batch run (`run_pipeline.py`) collects and processes the whole day in minutes, with no broker, no always-on
streaming job and no extra machines to run and watch. Streaming would add that operating cost without a business
benefit for these sources.

## 6. Where streaming would fit
The company sells 24/7 plant monitoring as a paid extra service. Inverters report readings every 1 to 5 minutes (the
interviewer's example, confirmed only briefly by the representative). An illustrative estimate, not measured: 10
plants x 20 inverters x one reading a minute x about 200 bytes.

| | Plant monitoring (estimate) | Today's file arrival (measured) | Factor |
|---|---:|---:|---:|
| Items per day | 288,000 readings | 13.2 files | about 22,000x |
| Data per day | 57.6 MB | 0.074 MB | about 780x |
| Items per year | 105,120,000 | about 4,800 | |
| Data per year | 21.0 GB | about 27 MB | |

These readings are a continuous stream of small events, and an alert (an inverter that stops) is only useful within
minutes. That is the case Kafka and Spark Streaming are made for, and where a nightly batch would be too late.

## 7. Streaming design sketch (not built)
```text
inverter portals / data loggers
   |  one message per reading (plant, inverter, time, power, status), about 200 bytes
   v
Kafka topic plant-readings (partitioned by plant)
   |
   v
Spark Structured Streaming, 1-minute windows per inverter
   |-- alerts: an inverter with no power or no reading in its window -> notification
   |-- every reading, as written, -> /lake/raw/plant_readings/<yyyy>/<mm>/<dd>/ (files per window)
   v
the existing nightly jobs read the raw files like every other source -> clean zone -> warehouse (daily yield)
```

The current zones already take it: the raw zone stores any source unchanged by date, the clean zone and the
warehouse are partitioned by date, and the nightly pipeline would treat the stream's files as one more source. Only
the alert path needs to run continuously. None of this is built: no Kafka topic, no streaming job and no plant data
exist in the demo.

## 8. Limits
- The arrival rates come from the synthetic main dataset, generated to match the company's description; the real
  rates (for example 80 statement files a month instead of 33) differ, but stay files a day, not events a second.
- `business_date` is the date a file belongs to (statement date, invoice issue date, photo date), not the time it
  reached the company's mailbox or Drive; the demo has no real arrival times.
- The monitoring volume is an estimate from assumed numbers, not measured data.

## Files
`arrival_rates.sql` (the three queries), `run_e4.py` (runs them, writes the CSVs), `results.csv` (per source and
month), `summary.csv` (per source and all sources), tests in `tests/ingest/test_e4.py`.
