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
Hive has no such order: it opens the ORC file and filters all 30,876 rows by `project_code` and `taken_at`, and it
plans and runs a query each time. On this dataset HBase also won the aggregation, which we did not expect.
Hive's time is almost all fixed cost: the same GROUP BY over only the 333 videos took 1.73 s (median of 5 warm
runs, measured once and not in results.csv), about the same as over all photos, because each GROUP BY starts a
MapReduce job. HBase's full scan grows with the rows it returns, 0.27 s for the 333 videos against 1.01 s for
all photos, as every row crosses Thrift and is summed in Python. So Hive's columnar scan and aggregation only
pays off once the data is large enough to hide its fixed cost, which 31,000 photos are not; this experiment did
not measure where that crossover lies. For the company: search and "show me this project's photos" belong in
HBase, while reports and aggregations stay in Hive: they are one SQL statement there instead of custom scan
code, and HBase's aggregation cost rises with every photo added while Hive's is mostly fixed at this size.
