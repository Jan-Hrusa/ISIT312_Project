# Log

One entry per merged task (or part with its own checkpoint), newest first:

    ### <date> - Task N: short name (your name)
    - Merged: what is now in integration
    - Checked: which tests / validation steps ran

### 2026-11-15 - Task 18: Photo packing into SequenceFiles (Muhammad)
- Merged: ingest/seqfile.py (write_seq: one real SequenceFile through the Hadoop API, key Text = photo name, value BytesWritable = bytes; read_seq), ingest/media_pack.py (pack: photos grouped by business date into <LAKE_RAW>/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq, a day already packed gets <yyyy-MM-dd>__<ingest ts>.seq, one ingest_log row per photo with every column), tests/ingest/test_media_pack.py; collect.py already loads ingest.media_pack, so it is unchanged
- Checked: not run in the client container (no Docker on my laptop, Jan validates); ruff check and format clean; the grouping checked on the 11 fixture photos with Spark stubbed out (7 daily files)

### 2026-11-15 - Task 17: Review fixes to the dataset statistics and the x10 dataset (Jan)
- Merged: `generators/scale.py` runs on the stack's Python 3.10 (`timezone.utc`; `from datetime import UTC` broke
  the import, so `pytest -m "not integration"` stopped at collection); paths and seed from `common.config`
  (new `config.dataset_dirs`); only `--scale 10` (the one scaled dataset config knows); the run refuses non-empty
  `sources_x10/` / `out_x10/` (files of an earlier run would end up in the statistics and the manifest); after
  generating it compares the data with `docs/x10-MANIFEST.sha256` and prints `OK` or the differing entries;
  `--check` repeats the comparison; `--record` rewrites the manifest and the x10 section (only for the repo);
  rewriting the scale-1 section keeps the blank line before the x10 section. `docs/dataset-stats.md`
  regenerated in the stack image (Python 3.10.12, 13.4 minutes) with the new instructions; the manifest is
  unchanged. `test_scale_multiplies_invoices` checks the doubled offers per year and the invoices per signed
  project (+-5%) instead of the total (which is 1.90x at scale 2 by design); two new tests
- Checked: tests/generators/test_scale.py 5 passed (3 of them fail on the PR #38 version); pytest -m "not
  integration" 166 passed, 1 skipped; ruff clean. In the stack image: x10 generated with `--scale 10 --record`, its 8,727
  manifest lines identical to Jayden's manifest from Python 3.13 (photos included), `--check` OK; scale 1
  regenerated and `--stats` leaves the doc unchanged

### 2026-11-15 - Task 17: Planted problems, dataset statistics, experiment dataset (Jayden)
- Merged: generators/scale.py (--stats for the scale-1 tables, --scale 10 runs finance_docs, bank and media as subprocesses with FVE_DATASET=x10), docs/dataset-stats.md, docs/x10-MANIFEST.sha256, tests/generators/test_scale.py.
- Checked (on his PC with Python 3.13, not in the client container): 3 scale tests pass, ruff clean. Scale 1: 52,055 files, 293.5 MB. x10 generated: 401,671 files, 2.78 GB (3.3 GB on disk). Two scale-2 runs gave an identical manifest.

### 2026-11-15 - Task 12: Review fixes to the HBase catalogue design (Jan)
- Merged: videos, documents and drawings are keyed at 00:00:00 of their date (was 12:00; photos keep their
  `taken_at`); the sample rows carry the codes Task 19 writes: `meta:filing_rule` `GPS` / `NONE` / `FOLDER` (the
  video too) and `doc:doc_type` `CONTRACT` / `PERMIT` / `GRID` / `HANDOVER` / `DRAWING`; `catalogue.cells` writes
  floats (the coordinates) with 6 decimals, so the Task 19 load and the samples store the same text;
  `hbase/schema.md` lists the codes and says that date ranges are UTC days; `docs/contracts.md` (shared file) now
  has the `filing_rule` and `doc_type` value sets (section 6) and the key-time and value-format rule of
  `media_catalog` (section 8); two new tests in `tests/hbase/test_rowkey.py`
- Checked: pytest tests/hbase 7 passed on the stack (core + hbase; the two new tests fail on the old `hbase/`);
  pytest -m "not integration" 161 passed, 1 skipped (the HBase test, no stack); ruff clean; `check.sh` OK hbase;
  HBase shell on the 18 sample rows: describe (4 families, VERSIONS 1), count 18, photo range scan, drawing,
  `UNASSIGNED` and video prefix scans (screenshots in Drive `Screenshots/catalogue/`)

### 2026-11-15 - Task 12: HBase catalogue design and test table (Aryen)
- Merged: hbase/schema.md (row key, four families, why project-first and zero-padded time, the two questions as
  scans); hbase/catalogue.py (connect, create_table, row_key, scan_bounds, prefix, cells, thumbnail);
  hbase/create_table.py; hbase/sample_rows.py (18 rows from the Task 7.1 samples); tests/hbase/test_rowkey.py
- Checked: tests/hbase 5 passed (test_sample_rows_roundtrip on the stack's HBase); pytest -m "not integration"
  150 passed; ruff check and format clean; check.sh core + hbase OK; in the HBase shell describe 'media_catalog'
  (4 families, VERSIONS 1), count 18, a range scan of FVE-2026-02 photos 15 Apr - 20 May (2 rows, in time
  order) and the drawing prefix scan (v1, v2, final)

### 2026-11-15 - Task 22: Review fixes to the OLAP queries (Jan)
- Merged: `expected/q1_budget_vs_actual.csv` has the missing subtotal row of FVE-2026-03; every query test now
  compares the result with its `expected/<query>.csv` (column names and rows); q5 also returns one row per signed
  year (project_code NULL; the year's spending divided by the year's MWp); q4 `avg_overrun_pct` is the average
  over the projects that are over budget (was over every COMPLETED project, which shrinks it towards 0 on the
  full data); q6 has `month_on_month_pct` and the previous value is named `prev_month_with_spend` (a month
  without invoices is skipped); every output column has an explicit name, so Hive and Spark SQL print the same
  headers; `sample_fill.sql`: invoice ids `<ico>-<number>`, due dates 14 days after the issue date, payment
  statuses PAID / PARTLY_PAID / UNPAID / OVERDUE, one bank account and 27 payments in `fact_payment` (for the
  V3/V4 queries of Task 30.1); the expected CSVs end with a newline
- Checked: pytest tests/warehouse/test_queries.py 10 passed (the q1 test fails on the old CSV); pytest -m "not
  integration" 155 passed; ruff clean; all seven queries on HiveServer2 against the sample database give
  the rows and the column names of the expected CSVs

### 2026-11-15 - Task 22: OLAP queries (Maysoon)
- Merged: `warehouse/queries/` with six OLAP queries (q1 budget vs actual with ROLLUP, q2 category group by year
  with CUBE, q3 cumulative spend, q4 overrun ranking, q5 cost per MWp, q6 month on month), the V1 project-list
  query with the traffic light, `sample_fill.sql` (3 projects, 4 categories, 36 invoice lines from November 2025
  to February 2026) and seven expected CSVs; `tests/warehouse/test_queries.py`
- Checked: pytest tests/warehouse/test_queries.py; pytest -m "not integration" 129 passed; ruff clean; q1 and v1
  run in beeline on HiveServer2 with the sample database (screenshots in Drive `Screenshots/dashboard/`)

### 2026-11-15 - Task 14.1: Collection job (Jan)
- Merged: `ingest/collect.py` `collect(spark, sources_dir, sources, dry_run)` copies every new file of `sources/`
  into the raw zone once (de-duplicated by source, original path and SHA-256; an existing target is an error) and
  appends one `ingest_log` row per file; `ingest.run(spark)` returns `files_new` and `files_skipped`; run by hand
  with `python -m ingest.collect [--sources ...] [--dry-run]`. `common/hdfs.py` (Hadoop FileSystem API through
  Spark's JVM, snapshot helpers included) and `common/lake.py` (`raw_path`, `append_ingest_log`,
  `current_raw_files`) are implemented. Photos are handed to `ingest.media_pack.pack` (Task 18); until that
  module exists they are reported as `photos: SKIPPED (packer not merged)` and not logged
- Checked: pytest tests/ingest tests/common/test_lake.py tests/common/test_hdfs.py (the 8 named tests and 16
  more), pytest -m "not integration" 145 passed, ruff clean. On the stack with the scale-1 data (seed 312): 21,179
  files collected in about 6 minutes, a second run collects 0; every raw file size equals its log row;
  `current_raw_files` feeds `processing.finance.run` (4,674 invoices, 2 PARSE_ERROR); snapshot allow, create,
  list and delete work on `/lake/raw`
### 2026-11-14 - Task 8: Review fixes to the full Docker stack and setup guide (Jan)
- Merged: `zeppelin` no longer depends on `hbase`, so `--profile core --profile zeppelin` starts (it was an invalid
  project); check.sh runs the YARN checks again when the yarn profile is up and drops a leftover check_hb table
  first; HBase runs from docker/hbase/start.sh (master in the foreground with the Thrift server; the container
  exits and restarts when either dies; Thrift heap 256m so both JVMs fit in 1 GB; clean stop); interpreter.json is
  mounted as a seed and copied into conf/ at every start (Zeppelin rewrites the file, so a bind mount of the file
  itself fails); stack Dockerfile: ARG HBASE_VERSION moved down to the HBase layer (the Hadoop and Spark layers
  keep their cache) and HBase downloaded from hbase/<version>/ instead of hbase/stable/; README restored
  (truncated) with the new services, PySpark note and disk sizes; SETUP.md converted to plain Markdown with the
  per-area profiles, branch and same-mirror rules, Windows disk compaction and every member in the machine table;
  final newlines
- Checked: fresh compose project with the rebuilt images: check.sh all OK with core + zeppelin, with core + hbase +
  zeppelin and with core + yarn; Zeppelin %hive, %sparksql and %python (happybase) paragraphs succeed; HBase keeps
  a table across stop/start, recreate and a killed master (restart count 1); the pre-#29 Dockerfile's apt, Hadoop
  and Spark layers are CACHED from the new build; pytest -m "not integration" 121 passed in the new client image

### 2026-11-14 - Task 8: Full Docker stack and setup guide (Ryan)
- Merged: Docker stack extended with HBase 2.5.16, HBase Thrift interface, Spark Thrift Server and Zeppelin 0.11.2;
  HBase configuration; Zeppelin Dockerfile with HappyBase, pandas and Hive JDBC driver; Hive, SparkSQL and Python
  interpreters; updated docker-compose.yml, check.sh, README.md and new SETUP.md covering Windows, macOS and Linux
  setup.
- Checked: HBase table creation, write, read and deletion tested successfully; Zeppelin %hive and %sparksql SHOW
  DATABASES queries returned default; Zeppelin %python successfully connected to HBase through HappyBase;
  ./check.sh reported 7 OK and 2 SKIP (YARN and Hive-on-YARN).

### 2026-11-14 - Task 7: Review fixes to the media generator and samples (Jan)
- Merged: the media generator follows the Task 7 output table: 1% of photos WRONG_SITE at 2-5 km from their own
  site and outside every project's radius (was 5 photos 10+ km away); 100-150 photos in the first construction
  week, then 3-8 a week on one workday; building permit = start - 30 days, grid connection = start + 60 days;
  drawings v1 = signed + 10, v2 = signed + 25, final = later of v2 + 10 and start - 5, planted final 20 days
  before v2, 20-60 KB; 3-5 videos per project. Task 7.1 samples: 4 more photos (2 inside FVE-2026-02, a second
  without GPS, one 3 km away = WRONG_SITE), permit and drawings re-dated by the rules, grid_connection.pdf added;
  README, mtimes_media.csv and tests updated (new: test_photos_first_week_then_weekly,
  test_documents_dated_by_the_rules)
- Checked: pytest -m "not integration" passed in the client image; ruff check and format clean; the new and
  changed tests fail on the old generator; scale-1 run: 30,876 photos, 3,088 without GPS, 309 wrong site (2.0-5.0
  km from their site, none inside any radius), 101-150 photos in each completed project's first week, 333 videos,
  every document and drawing dated by the rules; Validate screenshot (3 generated photos on the map of their
  site) in Drive Screenshots/media/

### 2026-11-14 - Task 7.1: Media and document samples (Muhammad)
- Merged: sample.mp4, 7 sample photos, the FVE-2026-02 folder (contract, permit, 3 drawings, 1 video), mtimes_media.csv, README with expected values, tests/generators/test_media_fixtures.py
- Checked: tests run outside Docker (piexif stand-in); not yet in the client container

### 2026-11-14 - Task 7: Media generator (Muhammad)
- Merged: generators/media (photos with EXIF and GPS, videos, documents, drawings, planted_media.csv) and tests/generators/test_media_generator.py
- Checked: same as above; a full scale-1 run gave 27,448 photos (2,745 without GPS, 5 wrong site), 328 videos, 316 documents, 249 drawings

### 2026-11-12 - Task 17.1: Review fixes to the planted finance problems (Jan)
- Merged: MISSING_VS picks only invoices due at least 6 days before DATA_END, so the bank generator pays all of them with an empty VS and Task 25 sees each as OVERDUE with an unmatched payment on DATA_END (one invoice was due 14 Nov 2026); new test test_missing_vs_invoices_are_due_in_time_to_be_paid (scale 1 and 2); whitespace line after Jayden's log entry removed
- Checked: pytest -m "not integration" passed; ruff check and format clean; the new test fails on the old planted.py; scale-1 run of the finance and bank generators: Task 9's match_invoice on the parsed bank files gives 10 NO_VS invoices OVERDUE with 10 UNMATCHED_PAYMENT, 10 ORDER_NOT_CLEARED, 15 WRONG_VS

### 2026-11-12 - Task 17.1: Planted finance problems (Jayden)
- Merged: generators/finance_docs/planted.py (OVERRUN 6, NO_PROJECT 25, DUPLICATE 5, MISSING_VS 10, PARSE_ERROR 2, counts x scale), planted.apply called from __main__.py (CLI plants by default, --no-planted switches it off), resent and truncated ISDOC files, out/ledger/planted_finance.csv, tests/generators/test_planted.py
- Checked: pytest tests/generators passed (the 4 named tests plus file checks for resent, truncated, blank-project and no-VS invoices); ruff check and format clean; scale-1 run writes planted_finance.csv with the task's counts

### 2026-11-12 - Task 6: Review fixes to the bank generator (Jan)
- Merged: STA statements write `:28:` (decision of 12 Nov); an invoice without VS in the ledger (Task 17.1's MISSING_VS) is ordered and paid with an empty VS, written as `0` in the KPC item (docs/formats/kpc.md), so the generator no longer stops on it; WRONG_VS pays with two digits of the VS swapped (a VS no invoice uses), and planted_payments.csv names both; planted cases only on invoices due at least 6 days before DATA_END, so all 10 ORDER_NOT_CLEARED and every OVERDUE show on DATA_END; Obaid's log entry added
- Checked: pytest -m "not integration" passed; ruff check and format clean; scale-1 run with 10 empty VS: Task 9's match_invoice on the parsed files gives exactly the planted statuses (10 ORDER_NOT_CLEARED, 15 + 10 UNMATCHED_PAYMENT); finance and bank generators run with Task 17.1 (PR #25) merged

### 2026-11-12 - Task 6: Bank generator (Obaid)
- Merged: generators/bank (payment plan, statements with carried balances, GPC, STA, TXT and KPC writers, planted_payments.csv) and tests/generators/test_bank_generator.py
- Checked: the 10 tests in tests/generators/test_bank_generator.py; ruff check and format; a seed-312 scale-1 run (4,951 bank movements, 4,667 KPC orders)

### 2026-11-12 - Task 10: Review fixes to the warehouse DDL (Jan)
- Merged: tests/warehouse/test_ddl.py uses conftest's spark_hive (its own SparkSession reached the stack's metastore in the client container and stopped the shared test session) and checks every table's partitions and location; warehouse/sql.py: run_file(spark, path, **params), ${...} in comment lines no longer fails; ruff fixes; Screenshots/ removed from the repo (moved to the Drive folder Screenshots/warehouse/) and ignored; README physical design: the queries each partition column serves, Lab 5 B1-B5, the validation on the stack; Gokulsanjay's log entry added
- Checked: pytest -m "not integration" passed; tests/warehouse also pass in the client configuration with the stack down; ruff check and format clean; DDL on the Docker stack: 9 tables in fve_dw

### 2026-11-12 - Task 10: Warehouse DDL, SQL runner and physical design (Gokulsanjay)
- Merged: warehouse/ddl/fve_dw.sql (the nine external ORC tables of contracts section 8 with their partitions), warehouse/sql.py (render, named_queries, run_file), warehouse/etl/__init__.py, the physical design section of warehouse/design/README.md, tests/warehouse/test_ddl.py
- Checked: the 7 tests in tests/warehouse/test_ddl.py; DDL run on the Docker stack, SHOW TABLES IN fve_dw and DESCRIBE FORMATTED fve_dw.fact_payment in beeline

### 2026-11-12 - Task 13: Review fixes to the finance parsers (Jan)
- Merged: processing.finance.run parses the files on the executors (one binaryFiles call per 200 files, so one partition each; only parse issues and ISDOC names reach the driver), because it ran out of Java heap on the scale-1 data; a file whose date can't be read no longer gets a made-up date; ruff check and format fixes in processing/finance and tests/processing/test_finance.py; test_run_on_fixtures expects exactly 9 lines; new test_run_reads_only_listed_files; Riya's log entry moved here from processing/finance/log.md
- Checked: pytest -m "not integration" passed; ruff check and format clean; run() on the generator's scale-1 output (9,488 files): 4,655 invoices (466 PDF-only), 12,746 lines, 4,644 booked costs, 0 issues, in about a minute; Task 13 Validate on the Docker stack: SELECT COUNT(*) FROM fve_clean.invoices = 4

### 2026-11-12 - Task 13: Finance parsers (Riya)
- Merged: processing/finance: parsers for projects, suppliers, budgets, ISDOC, PDF-only invoices and the Money S3 export, and run(spark, inputs=None) writing the six clean tables and the finance dq_issues; tests/processing/test_finance.py
- Checked: the 8 tests in tests/processing/test_finance.py

### 2026-11-12 - Task 6.1: Review fixes to the bank sample files (Jan)
- Merged: MT940 statement tag `:28:` as in Česká spořitelna's specification (Jan's decision) in the STA fixture, its README and test, and docs/formats/sta.md (Task 16 accepts `:28:` and `:28C:`); the Air Bank specification linked in docs/formats/gpc.md; Obaid's log.md entry says what was merged and checked
- Checked: pytest -m "not integration" passed; ruff check and format clean

### 2026-11-12 - Task 6.1: Bank sample files (Obaid)
- Merged: docs/formats/gpc.md, sta.md, kpc.md, txt.md (field positions from the RB ABO and ČS MT940 specs); bank samples in tests/fixtures/sources (RB GPC with the 4 Task 5.1 invoice debits and 1 credit, a broken RB GPC, ČS STA, RB KPC with 4 orders, a TXT per statement), tests/fixtures/mtimes_bank.csv, tests/fixtures/bank/README.md, tests/generators/test_bank_fixtures.py
- Checked: test_bank_fixtures_match_readme passed; pytest -m "not integration" passed; ruff check and format clean (in Jan's review, on the branch rebased on integration)

### 2026-11-12 - Task 5.1: Review fixes to the finance sample set (Jan)
- Merged: the three ISDOC fixtures regenerated with the merged generator (isdoc.to_xml) from their own values, so their invoice lines carry the ISDOC 6.0.2 elements of PR #16 (LineExtensionTaxAmount, UnitPriceTaxInclusive, schema order); test_finance_fixtures_match_readme also checks that the line VAT adds up to the invoice VAT; whitespace line in log.md removed
- Checked: pytest -m "not integration" passed; ruff check and format clean; only those line elements differ from the merged fixtures, totals unchanged

### 2026-11-11 - Task 5.1: Finance sample set (Jayden)
- Merged: tests/fixtures/sources/ finance sample set (3 projects, 5 suppliers, FVE-2026-02 budget with all 10 categories, 3 ISDOC + PDF invoices with 1, 3 and 5 lines and 1 PDF-only, money_export_2026-W20.csv), tests/fixtures/out/ledger/invoice_ledger.csv, tests/fixtures/mtimes_finance.csv, tests/fixtures/finance/README.md with the expected values
- Checked: test_finance_fixtures_match_readme passes; pytest tests/generators passed; ruff check and format clean; invoice totals checked by hand against the README

### 2026-11-11 - Task 5: Review fixes to the finance generator (Jan)
- Merged: generators/finance_docs/isdoc.py: invoice-line elements named and ordered as in the ISDOC 6.0.2 schema (LineExtensionTaxAmount instead of LineExtensionAmountTax, new UnitPriceTaxInclusive); test_isdoc_parses_and_totals_match_lines checks the names and their order; log.md entries in date order
- Checked: pytest -m "not integration" passed; ruff check and format clean; generator run at scale 1 twice, same bytes

### 2026-11-11 - Task 5: Finance sample set and full generator (Jayden)
- Merged: generators/finance_docs (master, budgets, plan, isdoc, pdf_invoice, money_export, ledger, util, __main__): projects, suppliers, budgets, ISDOC + PDF invoices, weekly accounting export and invoice_ledger.csv from one seeded rng; tests/generators/test_finance_docs.py
- Checked: pytest tests/generators passed; ruff check and ruff format --check clean; scale 1 run gives 95 projects, 35 suppliers, 83 budgets, 4655 invoices (466 PDF only), 559 export files; ISDOC, PDF and budget compared in Screenshots/finance/

### 2026-11-11 - Task 10.1: Review fixes to the warehouse design (Jan)
- Merged: warehouse/design/logical.uxf and logical.pdf: dim_date.iso_week STRING as in the contract, stray connector removed; README.md renders on GitHub and lists the hierarchies, the dashboard views each fact answers and all tables per view (V1 and V3 were incomplete); docs/contracts.md section 8: columns final, line_no INT, iso_week format YYYY-Www, the rule for fact_payment_order.cleared (from Task 26)
- Checked: docs only; every logical.uxf column and type matches contracts section 8 (script); README tables per view match docs/dashboard-design.md; README rendered with the GitHub Markdown API; logical.pdf re-exported with UMLet 15.1

### 2026-11-10 - Task 10.1: Warehouse conceptual and logical design (Gokulsanjay)
- Merged: warehouse/design/: conceptual and logical UMLet designs (conceptual.uxf, conceptual.pdf, logical.uxf, logical.pdf) and README.md (grains, measures, dimensions, dashboard views)
- Checked: Reviewed the four fact tables, five dimensions, keys, data types, hierarchies, and date relationships.

### 2026-11-10 - Task 11: Review fixes to the dashboard design (Jan)
- Merged: docs/dashboard-design.md: V3 needs no payment-allocation rule (one project and one category per invoice), V4 takes payment status from any line, V5 follows Task 22 (query file per row, monthly per project, q4/q5 on COMPLETED projects, note on months without invoices), the mock-up's region filter and search are not built; docs/contracts.md sections 6 and 8 state the one-project-one-category rule and the invoice-level payment status
- Checked: docs only; every warehouse column named in dashboard-design.md exists in contracts section 8 (script)

### 2026-11-10 - Task 11: Management dashboard design (Maysoon)
- Merged: docs/dashboard-design.md (views V1–V5: columns, calculations, traffic light, warehouse mappings) and docs/dashboard-mockup.png (V1 project list and V2 project detail)
- Checked: git diff --cached --check passed for both deliverables; documentation-only task, no code tests required
### 2026-11-09 - Task 9: Payment matching rules and tests (Mudabbir)
- Merged: processing/matching/rules.py (Invoice, Payment, Order, MatchResult, match_invoice: PAID / PARTLY_PAID / ORDERED / UNPAID / OVERDUE, order clearing, UNMATCHED_PAYMENT and ORDER_NOT_CLEARED issues); 14 named tests; 6 hand-made cases in tests/fixtures/matching/cases.json
- Checked: pytest tests/processing 19 passed; pytest -m "not integration" 43 passed; ruff check and format clean
### 2026-11-09 - Task 2: Start-of-session rule (Jan)
- Merged: AGENTS.md §3 and README: update before any work (also only running or checking): commit, fetch, rebase on origin/integration, `git rebase --abort` on a conflict, rebuild the images after new commits with the same mirror as the first build, fix for branches created without --no-track; docker/README: rebuild row and why the mirror must stay the same
- Checked: rebuild with the same APACHE_MIRROR fully cached (4 s), a different value rebuilds the stack image (5 min); check.sh core all OK on the rebuilt image; docs only otherwise

### 2026-11-09 - Task 3: check.sh pipelines without grep -q (Jan)
- Merged: docker/check.sh: no pipeline ends in `grep -q` any more. With `set -o pipefail`, grep's early exit made the feeding `docker compose exec` fail on the closed pipe, so `FAIL hdfs: WARNING: log4j.properties ...` came up at random although HDFS worked (found by a team member during first setup). Same fix in the HiveServer2 wait, check_hive (breaks once more databases exist) and the YARN detection (would skip the YARN checks silently)
- Checked: race reproduced on the old pipeline (producer exit 1 in 1 of 15 runs; member saw 255 every run), new pipeline 30 of 30 clean; deterministic demo exit 141 vs 0; check.sh core + yarn all OK

### 2026-11-09 - Task 2: AGENTS.md git and environment rules (Jan)
- Merged: AGENTS.md: new branches with --no-track then push -u; docker compose runs in docker/; scripts run as modules; out_x10/ never committed, fixtures committed
- Checked: docs only; no code changed

### 2026-11-08 - Task 2: Review fixes before the build starts (Jan)
- Merged: .gitignore anchored (tests/fixtures/sources/ was ignored) + out_x10/; fixture bytes kept (-text); get_spark(hive=False) in-memory; write_table refuses NULL-producing casts and drifted tables; load_projects names short rows; contracts examples, raw-zone fields, NO_PROJECT rule, warehouse types; README, PR template, docker/README, data-formats; ruff pinned
- Checked: image rebuilt; check.sh core + yarn 6 x OK; pytest 24 passed; ruff check and format clean

### 2026-11-08 - Task 3: Docker memory on Windows (Jan)
- Merged: docker/README.md Prerequisites say where to set Docker's memory: `.wslconfig` on Windows with WSL 2 (Docker Desktop has no setting there), Settings -> Resources on macOS
- Checked: docs only; WSL default (50% of RAM) and `.wslconfig` keys from Microsoft's WSL docs

### 2026-11-08 - Task 3: check.sh waits for the NameNode (Jan)
- Merged: docker/check.sh retries until the NameNode answers (it refused connections for the first seconds after up -d) and names the real error if it gives up
- Checked: check.sh straight after down + up -d: 4 OK (2 min); with the namenode stopped: FAIL stack naming UnknownHostException

### 2026-11-06 - Task 3: Docker starter stack (Jan)
- Merged: docker/ (stack and hive images, compose profiles core and yarn, conf, check.sh, README); README Setup, AGENTS.md section 4, pyproject (Python 3.10), requirements (pyspark==3.5.9, pyhive), .gitattributes
- Checked: check.sh all 6 OK on fresh volumes (core + yarn); pytest 21 passed and ruff in the client container; namenode 1 live datanode, yarn 1 active node, data kept after down/up

### 2026-11-05 - Task 2: Architecture freeze and data contracts (Jan)

- Merged: docs/contracts.md; common/ config, schemas, tables, spark, projects, dq (hdfs, lake as signatures for 14.1); tests/conftest.py fixtures, tests/fixtures/make_sources.py
- Checked: pytest (21 passed, no stack), ruff check, ruff format --check; Validate (beeline on the stack) after Task 3

### 2026-11-05 - Task 1: AI agent reading order (Jan)
- Merged: AGENTS.md sections 2 and 3: agents read the ClickUp guide page, then the task, then Drive 00 and 02, then README and contracts
- Checked: docs only; no code changed

