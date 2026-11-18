# E3: HBase vs Hive for media questions

The same two questions against the HBase catalogue `media_catalog` and the Hive table `fve_clean.media_files`, on
the main (scale-1) dataset: 30,876 photos, 83 projects. `python -m benchmarks.e3.run_e3` in the client container
(core + hbase profiles, after the `media` and `catalogue` steps); 10 runs per question and store on one open
connection, run 1 reported as cold, the median over runs 2-10. Both stores returned the same rows for both questions
(checked by the script). Raw times: [results.csv](results.csv).

| Question | HBase cold / median | Hive cold / median | Rows |
|---|---|---|---|
| Q1 photos of one project in one month (FVE-2026-02, June 2026) | 0.275 s / **0.108 s** | 0.452 s / 0.353 s | 146 |
| Q2 photos and MB per project and month (all photos) | 2.189 s / **1.009 s** | 2.031 s / 1.690 s | 1,052 groups |

HBase answers the lookup about 3x faster because of the row key: the project and the zero-padded time come
first, so "FVE-2026-02 in June" is one contiguous range of the sorted rows, and it reads only those 146 rows.
Hive has no such order: it filters all 30,876 rows of the ORC file by `project_code` and `taken_at`, and it plans
and runs a query each time.

## Q2 at more photos

On the main dataset HBase also won the aggregation, which we did not expect, so `python -m benchmarks.e3.scale_q2`
repeats Q2 with the photo rows copied 1, 2, 5, 7 and 10 times into scratch stores (metadata only: the file_id gets
`-<k>`, so every project and month keeps its groups and the counts multiply; the copies are dropped afterwards).
10 runs per factor and store, median over runs 2-10, both stores agreeing every time. Measured on the team lead's
desktop stack on 18 Nov 2026, a different machine from the table above, so compare within this table only. Raw
times: [results_scale.csv](results_scale.csv).

| Copies | Photos | HBase median | Hive median |
|---|---|---|---|
| 1x | 30,876 | **0.228 s** | 1.406 s |
| 2x | 61,752 | **0.461 s** | 1.247 s |
| 5x | 154,380 | **1.151 s** | 1.420 s |
| 7x | 216,132 | 2.257 s | **1.573 s** |
| 10x | 308,760 | 2.274 s | **1.262 s** |

Hive's time hardly moves (about 1.2-1.6 s at every size): it is almost all fixed cost, because HiveServer2 runs
each GROUP BY as a MapReduce job (local mode in the `core` profile; on YARN each job also waits for containers,
so we expect more). HBase's scan grows in step with the photos, about 0.23 s per 30,000 (the 7x HBase time is an
outlier: an earlier run gave 1.55 s), because every row crosses Thrift and is summed in Python. The two meet
between 5x and 7x the main dataset (about 150,000-220,000 photos); from there Hive wins and its lead grows with
every photo added, and in all three runs of the script 5x was still HBase's and 10x Hive's. For the company:
search and "show me this project's photos" belong in HBase, while reports and aggregations belong in Hive, where
they are one SQL statement instead of custom scan code and their cost does not grow with the photo archive.
