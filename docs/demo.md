# Demo: the data lake end to end (Task 33.1)

How to rebuild the whole lake from nothing on the scale-1 dataset, check that a second run changes nothing, and
walk the eight demo steps of the ClickUp guide page. Every number below comes from the run on a fresh stack on
19 Nov 2026 (team lead's desktop: 16 GB RAM, Docker Desktop, sources on a hard disk); use them to see at a glance
whether your run behaves the same. Screenshots of every screen: Drive `Screenshots/platform/T33.1_*.png` (also the
fallback if the stack fails during a presentation).

Demo project: **FVE-2016-01** (red: EARTHWORKS at 127.4 % of its budget), photos **1 May - 31 Jul 2016** (185
photos), drawing warning on **FVE-2022-08** (the planted wrong version).

## 1. Before you start
- Docker Desktop with about 8 GB for Docker: profiles `core` (~4.5 GB), `hbase` (~1 GB) and `zeppelin` (Zeppelin
  + Spark Thrift Server, ~2.5 GB). YARN is not needed for the demo.
- Your branch up to date with `integration` and the images built (`AGENTS.md` section 3).
- About 1.5 hours for a fresh build (section 2); after that the demo itself (section 4) needs only the running
  stack.
- Run every `docker compose` command in `docker/`. In plain Git Bash put `MSYS_NO_PATHCONV=1` in front of
  commands with `/lake/...` arguments, or Git Bash rewrites them into Windows paths.

## 2. Build the lake from nothing
The first command deletes the stack's volumes (HDFS, the Hive metastore, HBase): everything in the lake is
rebuilt from the generators, nothing else is lost. Start with empty `sources/` and `out/` folders in the repo
(move or delete the old ones), so no file from an older generator version is collected.

```bash
cd docker
docker compose --profile core --profile yarn --profile hbase --profile zeppelin down -v
docker compose --profile core --profile hbase --profile zeppelin up -d
./check.sh                                            # OK lines; SKIP for yarn and hive-yarn is expected

docker compose exec client python -m generators.finance_docs
docker compose exec client python -m generators.bank
docker compose exec client python -m generators.media
docker compose exec client python run_pipeline.py --all        # run 1
```

| Step | Time (19 Nov) | What it prints at the end |
|---|---:|---|
| `generators.finance_docs` | 141 s | invoices 4669 (PDF only 467); planted OVERRUN 6, NO_PROJECT 25, DUPLICATE 5, MISSING_VS 10, PARSE_ERROR 2 |
| `generators.bank` | 136 s | transactions 4966, orders 4682; planted BAD_FILE 1, INSTALMENTS 93, LATE 139, NEVER 46, NO_VS 10, ORDER_LOST 10, PARTIAL 46, WRONG_VS 15 |
| `generators.media` | 391 s | photos 30876 (with GPS 27788, of them wrong site 309; without GPS 3088), videos 333, documents 321, drawings 248 |
| `collect` | 1353 s | files_new=52055, files_skipped=0, snapshot=1 |
| `bank` | 164 s | bank_transactions=4965, bank_tx_details=4965, payment_orders=4682, issues=1 |
| `finance` | 390 s | projects=95, suppliers=35, budget_lines=830, invoices=4669, invoice_lines=13244, booked_costs=4658, dq_issues=58 |
| `matching` | 161 s | invoices=4669, paid=4508, due=4635, issues=35 |
| `media` | 461 s | media_files=31209, documents=569, issues=3398 |
| `warehouse` | 90 s | fact_budget_line=830, fact_invoice_line=13244, fact_payment=4672, fact_payment_order=4682, checks_failed=0 |
| `catalogue` | 546 s | rows=31778 |
| whole pipeline | 3177 s | `pipeline OK ... (7 steps, 0 skipped)` |

The step times depend on the machine and on which profiles run beside the client (on 16 Nov the same steps took
66 s for bank and 195 s for finance). The generators are deterministic: the 52,055 files were byte for byte the
same as an earlier generation.

## 3. Run it again: nothing may change
```bash
docker compose exec client python run_pipeline.py --all        # run 2: 2095 s on 19 Nov
```

`collect` must report `files_new=0, files_skipped=52055, snapshot=1`, and every other step the same counts as
run 1. Then compare the warehouse totals and the data-quality issues after each run (HiveServer2, about 45 s):

```bash
docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000 -n hive --silent=true --outputformat=tsv2 -e "
SELECT 'fact_invoice_line' AS fact_table, COUNT(*) AS row_count, CAST(SUM(amount_net) AS STRING) AS total FROM fve_dw.fact_invoice_line
UNION ALL SELECT 'fact_budget_line', COUNT(*), CAST(SUM(budget_amount) AS STRING) FROM fve_dw.fact_budget_line
UNION ALL SELECT 'fact_payment', COUNT(*), CAST(SUM(amount) AS STRING) FROM fve_dw.fact_payment
UNION ALL SELECT 'fact_payment_order', COUNT(*), CAST(SUM(amount) AS STRING) FROM fve_dw.fact_payment_order;
SELECT job, issue_type, COUNT(*) AS issues FROM fve_clean.dq_issues GROUP BY job, issue_type ORDER BY job, issue_type;"
```

Both runs gave exactly this:

| Fact table | Rows | Total |
|---|---:|---:|
| fact_invoice_line (`amount_net`) | 13,244 | 2,312,351,039.07 |
| fact_budget_line (`budget_amount`) | 830 | 2,641,905,917.00 |
| fact_payment (`amount`) | 4,672 | 2,737,761,707.22 |
| fact_payment_order (`amount`) | 4,682 | 2,743,570,744.78 |

| Job | Issue types (count) |
|---|---|
| bank | PARSE_ERROR 1 |
| finance | DUPLICATE 5, MISSING_VS 10, NO_PROJECT 34, OVERRUN 7, PARSE_ERROR 2 |
| matching | ORDER_NOT_CLEARED 10, UNMATCHED_PAYMENT 25 |
| media | NO_GPS 3088, UNASSIGNED_PHOTO 309, WRONG_VERSION 1 |

OVERRUN 7 = the 6 planted overruns + FVE-2025-08/INVERTERS (the accepted `SINGLE_ACTIVE` effect, Task 20).
`pytest -m integration` in the client needs exactly this state: 4 passed (61 s).

Before the demo, restart the two services that cache table metadata, so they read the new tables:

```bash
docker compose restart sparksql zeppelin
```

## 4. The demo, step by step
Zeppelin: http://localhost:8080. Times are how long each paragraph took to run (REST run on 19 Nov, after the
restart); allow the talking time on top. The first query after a restart is the slowest.

| Step | Show | Time |
|---|---|---:|
| 1 | The synthetic company data in `sources/` | - |
| 2 | Collection into the raw zone | - |
| 3 | Spark jobs into the clean zone | - |
| 4 | Management dashboard: project -> category -> supplier -> invoices | ~67 s (+11 s V5) |
| 5 | "To fix" list | ~20 s (+10 s for the last three) |
| 6 | Search: photos with thumbnails, latest drawing, unassigned | ~9 s |
| 7 | Delete a raw folder and restore it from a snapshot | 16 s |
| 8 | Experiments E1-E5 | - |

**Steps 1-3: the data and the pipeline (prepared, not run live).** The full pipeline takes 35-55 minutes, so
show its result: the generator summaries (section 2), the run log `out/pipeline_<timestamp>.log`, and the raw zone
in the NameNode UI (http://localhost:9870, Utilities -> Browse the file system -> `/lake/raw`: one folder per
source, files unchanged with a collection timestamp in the name, photos packed into daily SequenceFiles under
`/lake/raw/photos`). Screenshot: `T33.1_02_pipeline_runs_and_totals.png`.

**Step 4: management dashboard** (`management_dashboard`, http://localhost:8080/#/notebook/2N8K6MZZH).
1. Run *Obnovit tabulky* (refresh, 10 s), then *V1 Projekty* (24 s): 83 projects, 7 red on top (FVE-2020-04,
   FVE-2022-03, FVE-2018-09, FVE-2016-01, FVE-2024-09, FVE-2017-03, FVE-2025-08), then 10 amber. The chart below
   shows budget vs spent per project.
2. In the note's forms at the top set **project** `FVE-2016-01`. *V2 Detail projektu* (7 s): EARTHWORKS budget
   2,632,171.00, spent 3,353,387.50, 127.40 %, red; the other nine categories green; the total row red (94.57 %,
   red because one category is).
3. Set **category** `EARTHWORKS`. *V3 Kategorie -> dodavatelé* (10 s): four suppliers; the first is IČO
   `34099227` (invoiced 2,151,763.26, all paid).
4. Set **supplier** `34099227`. *V4 Dodavatel -> faktury* (4 s): its invoices of this project and category,
   unpaid ones first (here 3 invoices, all PAID, summing to V3's 2,151,763.26; the project is finished).
   *Křivka čerpání* (4 s): monthly and cumulative spend from 2016-05.
5. Optional, V5 (3 paragraphs, 11 s): cost per MWp of the completed projects; categories most often over budget
   (EARTHWORKS first, 5 projects); spend by cost group and year.

Screenshots: `T33.1_04a` - `T33.1_04g`.

**Step 5: "to fix" list** (`to_fix`, http://localhost:8080/#/notebook/2NAFGU2WC). Run the paragraphs in order:
refresh; issues per type and job (11 rows, the table in section 3); unmatched payments with a suggested invoice
(25); invoices and booked costs without a project (34); payment orders never cleared (10); photos without
location and outside every site (sorted with the photos outside a site first; the first one, taken on 4 May
2016, lies 4,420 m from FVE-2016-01); final drawing older than a numbered version (1: FVE-2022-08 site layout);
duplicates (5), unparsable files (3), invoices without a variable symbol (10). The overdue view is the separate
`overdue_by_supplier` note (28 suppliers; enter a name or IČO in its form for one supplier's invoices).
Screenshots: `T33.1_05a` - `T33.1_05f`.

**Step 6: search** (`search`, http://localhost:8080/#/notebook/2N8QX2XVQ). Each paragraph has its own form.
1. *Fotky stavby za období*: project `FVE-2016-01`, from `2016-05-01`, to `2016-07-31` -> "185 fotek", the table
   with time, GPS and file name, and the first 6 thumbnails read from HBase (8 s).
2. *Poslední výkres*: `FVE-2022-08` -> `site_layout_final.dwg` with the red warning "v2 is newer than final"
   (0.1 s). With `FVE-2016-01` it shows the green "final is the newest version".
3. *Nezařazené*: PHOTO 3397 unassigned (= NO_GPS 3088 + UNASSIGNED_PHOTO 309), VIDEO, DOC and DRAWING 0 (1 s).

Screenshots: `T33.1_06a` - `T33.1_06c`.

**Step 7: snapshot restore** (a terminal next to Zeppelin):

```bash
docker compose exec client python -m ingest.restore_demo --project FVE-2016-01
```

It lists the project's 7 raw documents with HDFS checksums, checks the newest snapshot holds the same files,
deletes `/lake/raw/docs/FVE-2016-01` permanently (`-skipTrash`), copies it back from
`/lake/raw/.snapshot/raw-<timestamp>/docs/FVE-2016-01` and ends with `RESTORED 7 files, checksums match` (16 s). It
refuses and deletes nothing when no snapshot holds the folder or the newest one differs; then run the collection
again (`run_pipeline.py --steps collect`) to take a new snapshot. Screenshot: `T33.1_07_restore_demo.png`.

**Step 8: experiments.** Show the results tables in the READMEs (no live run):

| Experiment | README | One-line result |
|---|---|---|
| E1 MapReduce vs Spark vs Hive (x10 GPC statements) | `benchmarks/e1/README.md` | medians 28.2 / 53.9 / 155.1 s; identical output |
| E2 small files vs SequenceFiles (x10 photos) | `benchmarks/e2/README.md` | 583,682 vs 5,662 NameNode objects (0.97 %) |
| E3 HBase vs Hive for media questions | `benchmarks/e3/README.md` | HBase faster at today's volume; Hive wins Q2 from 5-7x the photos |
| E4 arrival rates vs streaming | `benchmarks/e4/README.md` | about 13 files a day: nightly batch, not streaming |
| E5 Hive on MapReduce vs Spark SQL (x10 warehouse) | `benchmarks/e5/README.md` | Spark 32-79x faster warm; same rows on both engines |

## 5. Things to know
- The *V1 Projekty* table is wider than a 1400 px screen: the traffic light and project are on the left, budget,
  spent and margin need a horizontal scroll (or zoom the browser out).
- The "photos without location" paragraph shows Zeppelin's "Output is truncated" banner: it lists about 3,400
  photos and Zeppelin cuts results above 100 KB. The rows most worth showing (outside every site) are sorted
  first; the counts paragraph has the full totals.
- In run 2 the log printed a `RetryingMetaStoreClient ... lost connection ... reconnect (1 of 1)` warning with a
  stack trace at the start of the bank step, after collect had kept the Spark session idle for about 7 minutes;
  the retry worked and every count was identical. It is noise, not a failure.
- The committed notes carry no saved form values, so a fresh Zeppelin shows the defaults (FVE-2026-02 / PANELS /
  empty supplier on the dashboard, FVE-2026-02 June 2026 and FVE-2022-08 in the search): type the demo values
  above each time.
- After a Zeppelin run, `git status` shows the four notes changed (results and form values written back): reset
  them (`git checkout -- notebooks/`) and never commit a run.
