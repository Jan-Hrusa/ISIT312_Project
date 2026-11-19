# E2: HDFS small files – loose photos vs daily SequenceFiles

The question: what does storing every site photo as its own HDFS file cost the NameNode, and how much do Task 18's
daily SequenceFiles save? The same photos are stored two ways, three runs each:

- **loose**: `hdfs dfs -put -t 8` of the photo folder into `/bench/x10/loose/`, one HDFS file (and one block) per
  photo;
- **packed**: the collection job with Task 18's packer (`ingest.collect.collect(spark, sources=["photos"])`), one
  SequenceFile per day under `/bench/x10/lake/raw/photos/<yyyy>/<mm>/`.

After each variant the script records the folder's files, directories and blocks (`hdfs dfs -count`, `hdfs fsck`),
the NameNode heap (JMX `MemHeapUsedM`), the write time and the time to read 100 random photos back (loose: open the
file; packed: find the day's file and key in `ingest_log`, then `read_seq` and filter). Every photo read back is
compared with its source file. Before each variant its folder is cleared (for packed also `/bench/x10/lake` and the
`fve_clean_x10.ingest_log` table), the only place in the project where deleting is allowed.

## How to run

In the client container with the core profile up (`docker compose --profile core up -d`):

```
python -m generators.scale --scale 10              # once: the x10 dataset (about 15 minutes, must print OK)
python -m benchmarks.e2.run_e2                      # scale-1 dry run (30,876 photos) -> results_main.csv
FVE_DATASET=x10 python -m benchmarks.e2.run_e2 --pause   # the experiment (291,840 photos) -> results.csv
```

`--pause` stops before and after each variant of run 1 for the NameNode UI screenshots
(http://localhost:9870, "Summary"; saved in Drive `Screenshots/benchmarks/`). The x10 run writes `results.csv` and
the table below; `python -m benchmarks.e2.run_e2 --summary` rebuilds the table from `results.csv`.
`python -m benchmarks.e2.namenode_stats <dir> ...` prints the NameNode numbers and a folder's objects at any time.

## Results (x10 dataset)

<!-- results:begin -->
| Variant | Files | Dirs | Blocks | Objects | ~150 B/object | NameNode heap after | Write | Read 100 random |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| loose | 291,840 | 2 | 291,840 | 583,682 | 87.6 MB | 134 MB | 5460 s | 7.65 s |
| packed | 2,761 | 140 | 2,761 | 5,662 | 0.8 MB | 164 MB | 1566 s | 20.95 s |

Packed objects are 0.97% of the loose objects (target: below 2%).

Medians of 3 runs per variant; raw values in [results.csv](results.csv).
<!-- results:end -->

"~150 B/object" is the usual rule of thumb for NameNode memory (every file, directory and block is an object held in
the NameNode's heap). The measured heap includes everything else the NameNode holds and drops only when the JVM
collects garbage, so it is reported next to the estimate, not instead of it.

## What it shows

The NameNode keeps the whole namespace in memory: every file, directory and block is an object of roughly 150
bytes, whatever the file's size. So HDFS runs out of NameNode memory because of the number of files, not their
size: a 8 KB photo costs the same two objects (a file and a block) as a 100 MB file. Stored loose, each photo adds
its own file and block, so the object count grows with every photo; packed, a day's photos share one file and
one block, so the count grows with the number of days instead. Writing loose photos also pays one NameNode
round trip to create and close every file, while packing writes one file per day. The price is random access:
a loose photo is one open and read, while a packed one needs its file and key from `ingest_log` and then a scan of
that day's SequenceFile, which has no index. Alternatives with the same saving: Hadoop Archives (HAR) pack files
behind an index but cannot be changed afterwards, a MapFile is a sorted SequenceFile with an index that allows
direct lookups by key, and HBase stores small blobs as cells (our catalogue already keeps the photo thumbnails
there).
