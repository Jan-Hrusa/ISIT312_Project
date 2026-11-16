# Data contracts

The names everyone builds against: paths, files, tables, columns, codes and module entry points. **This file wins
over any task description**; if they disagree, tell Jan so the task gets fixed. Change it only through a PR that
says why (it is a shared file).

The code imports the same values from `common/config.py` (settings, codes, paths) and `common/schemas.py` (table
columns); `tests/common/test_schemas.py` checks that the columns and partitions in section 6 below match
`common/schemas.py`. Read values
through the module (`config.CLEAN_DB`), never by copying them into your code.

Frozen with Task 2 on 5 Nov 2026; review fixes 8 Nov (examples, raw-zone fields, write rules); 10 Nov one project and category per invoice, invoice-level payment status (Task 11 review). Everything runs in the `client` container of the Docker stack (`docker/`, Task 3).

## 1. Project code and status
- Code `FVE-YYYY-NN`: YYYY = offer year (= signing year for signed projects), NN = 01-99 within that year;
  regex `config.PROJECT_CODE_RE` = `^FVE-\d{4}-\d{2}$` (check with `config.is_project_code()`), e.g. `FVE-2024-03`.
- Statuses (`config.PROJECT_STATUSES`): `ACTIVE`, `COMPLETED` (construction ended before `DATA_END`),
  `NOT_SIGNED` (an offer that wasn't won: no signing or construction dates, no budget, no costs).
- Every invoice line, budget line, booked cost, payment and photo carries a project code, or goes to the "to fix"
  list: `project_code` is NULL in `invoices`, `invoice_lines` and `booked_costs` when no rule matched, and
  `UNASSIGNED` (`config.UNASSIGNED`) in `media_files` and `documents`.
- Data period: `DATA_START` = 2016-01-01 to `DATA_END` = 2026-10-31 ("today" for the data); seed `SEED` = 312.

### Cost categories (`config.CATEGORIES`, exactly these 10 codes)
| Code | Name | Group |
|---|---|---|
| `PANELS` | Panels | technology |
| `INVERTERS` | Inverters | technology |
| `BATTERIES` | Batteries | technology |
| `STRUCTURES` | Mounting structures | construction |
| `CABLES` | Cables | construction |
| `EARTHWORKS` | Earthworks | construction |
| `GRID` | Grid connection | construction |
| `DESIGN` | Design | services |
| `SURVEY` | Survey | services |
| `OTHER` | Other | services |

### Banks (`config.BANKS`; the company's fake accounts)
| Code | Bank | Bank code | Company account | Format | Statements |
|---|---|---|---|---|---|
| `RB` | Raiffeisenbank | 5500 | 2101234567 | GPC | daily |
| `UCB` | UniCredit Bank | 2700 | 1387654321 | GPC | monthly |
| `KB` | Komerční banka | 0100 | 1234567890 | GPC | monthly |
| `CS` | Česká spořitelna | 0800 | 2900112233 | STA (MT940, CP852) | monthly |

Raiffeisenbank (`RB`) is the primary account: its GPC arrives every day, also on days without movements.

## 2. Money, time and codes
- Amounts in CZK, type `DECIMAL(14,2)`. In `bank_transactions` debits are negative and credits positive; in
  `payment_orders` amounts are positive (money the company told the bank to pay).
- Dates are `DATE` (`yyyy-MM-dd` in files); timestamps are `TIMESTAMP` in UTC (Spark session time zone UTC).
- Variabilní / konstantní / specifický symbol (`vs`, `ks`, `ss`): strings without leading zeros; empty -> NULL.
- Accounts: digits only, without leading zeros and without a prefix (no synthetic account has one); bank codes:
  4 digits with leading zeros (`0100`). The same form in every file and table.
- Supplier = 8-digit IČO (`ico`, `supplier_ico`, string). Currency `CZK`.
- Upper-case codes for every status, category, kind, rule and issue type.

## 3. IDs
| ID | Rule | Example |
|---|---|---|
| `invoice_id` | `<ico>-<number>` (number `YYYYNNNNN` per supplier, Task 5) | `12345678-202600001` |
| `tx_id` | `<bank>-<statement date yyyyMMdd>-<line no, 4 digits>` | `RB-20261002-0003` |
| `order_id` | `<kpc file base name>-<item no, 3 digits>` | `PO_2026-10-06_RB-001` |
| `file_id` | first 16 hex characters of the file's SHA-256 | `9f86d081884c7d65` |
| `issue_id` | random UUID (written by `write_issues`) | |
| `source_file` | in every clean table: the raw path of the file the row came from, exactly as in `ingest_log.raw_path` (no `hdfs://` scheme) | |

## 4. Source folders and files
`sources/` (`config.SOURCES_DIR`; `sources_x10/` for the 10x dataset) stands in for the company mailbox and
Google Drive. Generators write it; the collection job (Task 14.1) reads it. It is git-ignored.

| Folder | Files | Written by (task) |
|---|---|---|
| `sources/master/` | `projects.csv`, `suppliers.csv` | 5 |
| `sources/drive/budgets/` | `<project_code>_budget.xlsx` | 5 |
| `sources/mailbox/invoices/` | `<ico>_<number>.isdoc` + `<ico>_<number>.pdf` (about 10% PDF only) | 5 |
| `sources/drive/accounting/` | `money_export_<YYYY>-W<ww>.csv` (one per ISO week) | 5 |
| `sources/mailbox/bank/<RB\|UCB\|KB>/` | `<YY><NNN>_<account>_CZK.gpc` + `.txt` of the same base name | 6 |
| `sources/mailbox/bank/CS/` | `<YY><NNN>_<account>.sta` + `.txt` of the same base name | 6 |
| `sources/drive/payments/` | `PO_<yyyy-MM-dd>_<BANK>.kpc` (one per bank per payment run) | 6 |
| `sources/mailbox/photos/` | `IMG_<yyyyMMdd>_<HHmmss>_<nnnnn>.jpg` (names globally unique) | 7 |
| `sources/drive/projects/<project_code>/` | `contract.docx`, `building_permit.pdf`, `grid_connection.pdf`, `handover_protocol.pdf` (COMPLETED only), `site_layout_v1.dwg`, `site_layout_v2.dwg`, `site_layout_final.dwg` | 7 |
| `sources/drive/projects/<project_code>/videos/` | `VID_<yyyyMMdd>_<nnnnn>.mp4` | 7 |

- **Every generator sets each file's modification time to 12:00 UTC of its business date** (statement date,
  invoice issue date, payment-run date, the export week's Monday, photo `taken_at`, document date). The collection
  job takes the raw-zone month from the mtime; nobody parses dates out of file names for that.
- Every statement (GPC or STA) has a TXT of the same base name with one line per transaction:
  `<line_no>|<free text>`.

### Columns of the tabular source files
CSV files: UTF-8, header row; `master/*.csv` use `,` and a decimal point; the Money S3 export uses `;` and a
decimal comma. Booleans `true`/`false`.

| File | Columns (in this order) |
|---|---|
| `master/projects.csv` | `project_code`, `name`, `town`, `region`, `lat`, `lon`, `radius_m`, `mwp`, `has_battery`, `contract_value`, `offer_date`, `signed_date`, `construction_start`, `construction_end`, `status` |
| `master/suppliers.csv` | `ico`, `name`, `category`, `bank_account`, `bank_code` |
| `drive/budgets/<project_code>_budget.xlsx (sheet Budget)` | `project_code`, `category`, `amount_czk` |
| `drive/accounting/money_export_<YYYY>-W<ww>.csv` | `doc_ref`, `supplier_ico`, `vs`, `issue_date`, `due_date`, `booking_date`, `project_code`, `cost_centre`, `category`, `amount_net_czk`, `amount_gross_czk` |

### Truth files (not collected)
`out/ledger/` (`config.LEDGER_DIR`; `out_x10/ledger/` for the 10x dataset): `invoice_ledger.csv` (Task 5, one row
per invoice incl. the supplier account, the input for Task 6), `planted_finance.csv` (17.1), `planted_payments.csv`
(6), `planted_media.csv` (7). Tests of the catching tasks compare their counts with these files.

### Test fixtures
Small hand-checked files live in `tests/fixtures/sources/` in the same layout as `sources/`, with their business
dates in `tests/fixtures/mtimes_<area>.csv` (header `path,business_date`, path relative to `sources/`). Git keeps
no mtimes, so `tests/fixtures/make_sources.py` (fixture `sources_tree`) copies them to a temporary folder and sets
each mtime. Every fixture file needs a date there.

## 5. Raw zone (HDFS `config.LAKE_RAW` = `/lake/raw`)
- Path: `<LAKE_RAW>/<source>/<yyyy>/<mm>/<stem>__<ingest UTC yyyyMMddHHmmss>.<ext>`, yyyy/mm from the file's
  mtime (business month), e.g. `/lake/raw/bank_gpc/2026/01/26001_2101234567_CZK__20261114093000.gpc`
  (statement 26001 of January 2026, collected on 14 Nov 2026; `common.lake.raw_path`). Raw paths never carry
  a scheme: strip `hdfs://namenode:8020` from paths Spark reports (e.g. `binaryFiles` keys) before using them
  as `source_file` or `record_ref`.
- `docs` and `video` keep the project: `<LAKE_RAW>/docs/<project_code>/<yyyy>/<mm>/...` (the restore demo deletes
  and restores one such folder).
- Photos: daily SequenceFiles `<LAKE_RAW>/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq` (key Text = original name, value
  BytesWritable = bytes); a second batch for a day already packed gets `<yyyy-MM-dd>__<ingest ts>.seq` (Task 18).
- Write-once: nothing under `/lake/raw` is overwritten or deleted; an existing target path is an error.
- De-duplication by (source, original path, SHA-256): an unchanged file at the same path is skipped, a changed one
  gets a new raw file; identical bytes at different paths are all collected.
- Every collected file (and every packed photo) is one row of `ingest_log` (section 6): `run_id` = the run's
  start in UTC as `yyyyMMddHHmmss`; `original_path` relative to `sources/` with `/` separators (e.g.
  `mailbox/photos/IMG_20240512_101500_00042.jpg`); `business_date` = UTC date of the mtime.
- **Parsers take their file list from `common.lake.current_raw_files(spark, source)`** (latest version per
  original path), never by listing raw folders; each parser also accepts `run(spark, inputs=None)` with explicit
  paths for tests.
- Snapshots: `/lake/raw` is snapshottable; snapshot `raw-<run_id>` after every collection run of the main
  dataset; the last 30 are kept.

| Source key | From `sources/` | Raw path keeps the project |
|---|---|---|
| `master` | `master/*.csv` | no |
| `budgets` | `drive/budgets/*.xlsx` | no |
| `isdoc` | `mailbox/invoices/*.isdoc` | no |
| `invoice_pdf` | `mailbox/invoices/*.pdf` | no |
| `accounting` | `drive/accounting/*.csv` | no |
| `bank_gpc` | `mailbox/bank/*/*.gpc` | no |
| `bank_sta` | `mailbox/bank/*/*.sta` | no |
| `bank_txt` | `mailbox/bank/*/*.txt` | no |
| `kpc` | `drive/payments/*.kpc` | no |
| `photos` | `mailbox/photos/*.jpg` | no |
| `video` | `drive/projects/*/videos/*.mp4` | yes |
| `docs` | `drive/projects/*/*.*` | yes |

## 6. Clean zone (Hive database `fve_clean`, `config.CLEAN_DB`)
All tables are `EXTERNAL`, ORC, `LOCATION '<LAKE_CLEAN>/<table>'` (`/lake/clean/<table>`), created by
`common.tables.create_clean_tables(spark)`. Each job recomputes its tables on every run with
`common.tables.write_table(spark, df, table)`: contract columns in this order, cast to these types, missing column
= error, extra columns dropped, whole table overwritten. A value that can't be cast (e.g. a date in another
format) is an error, not a NULL; a table whose columns differ from this section (created before a contract
change) is an error: drop it and run `create_clean_tables` again. A job never overwrites a table it reads in
the same run (Spark refuses): compute the new content from other tables. Exceptions: `ingest_log` is append only
(`common.lake.append_ingest_log`), `dq_issues` is written per job (`common.dq.write_issues`, section 7).

| Table | Columns | Written by (task) |
|---|---|---|
| `projects` | `project_code` STRING, `name` STRING, `town` STRING, `region` STRING, `lat` DOUBLE, `lon` DOUBLE, `radius_m` INT, `mwp` DECIMAL(5,2), `has_battery` BOOLEAN, `contract_value` DECIMAL(14,2), `offer_date` DATE, `signed_date` DATE, `construction_start` DATE, `construction_end` DATE, `status` STRING, `source_file` STRING | 13 |
| `suppliers` | `ico` STRING, `name` STRING, `category` STRING, `bank_account` STRING, `bank_code` STRING, `source_file` STRING | 13 |
| `budget_lines` | `project_code` STRING, `category` STRING, `amount` DECIMAL(14,2), `source_file` STRING | 13 |
| `invoices` | `invoice_id` STRING, `supplier_ico` STRING, `number` STRING, `vs` STRING, `issue_date` DATE, `due_date` DATE, `total_net` DECIMAL(14,2), `total_vat` DECIMAL(14,2), `total_gross` DECIMAL(14,2), `currency` STRING, `category` STRING, `project_code` STRING, `project_rule` STRING, `has_isdoc` BOOLEAN, `source_file` STRING | 13 (parse), 20 (project_code, category, project_rule) |
| `invoice_lines` | `invoice_id` STRING, `line_no` INT, `description` STRING, `quantity` DECIMAL(12,3), `unit_price` DECIMAL(14,2), `amount_net` DECIMAL(14,2), `vat_rate` DECIMAL(4,2), `vat_amount` DECIMAL(14,2), `category` STRING, `project_code` STRING | 13 (parse), 20 (project_code, category) |
| `booked_costs` | `doc_ref` STRING, `supplier_ico` STRING, `vs` STRING, `issue_date` DATE, `due_date` DATE, `booking_date` DATE, `project_code` STRING, `cost_centre` STRING, `category` STRING, `amount` DECIMAL(14,2), `amount_gross` DECIMAL(14,2), `export_week` STRING, `source_file` STRING | 13 |
| `bank_transactions` | `tx_id` STRING, `bank` STRING, `account` STRING, `statement_no` INT, `statement_date` DATE, `line_no` INT, `value_date` DATE, `amount` DECIMAL(14,2), `counterparty_account` STRING, `counterparty_bank_code` STRING, `vs` STRING, `ks` STRING, `ss` STRING, `note` STRING, `source_file` STRING | 16 |
| `bank_tx_details` | `tx_id` STRING, `detail_text` STRING, `source_file` STRING | 16 |
| `payment_orders` | `order_id` STRING, `bank` STRING, `account` STRING, `order_date` DATE, `due_date` DATE, `amount` DECIMAL(14,2), `counterparty_account` STRING, `counterparty_bank_code` STRING, `vs` STRING, `ks` STRING, `ss` STRING, `source_file` STRING | 16 |
| `invoice_status` | `invoice_id` STRING, `status` STRING, `paid_amount` DECIMAL(14,2), `paid_date` DATE, `days_to_pay` INT, `days_late` INT, `order_ids` ARRAY<STRING>, `uncleared_order_ids` ARRAY<STRING>, `tx_ids` ARRAY<STRING>, `as_of` DATE | 25.1 |
| `media_files` | `file_id` STRING, `kind` STRING, `original_name` STRING, `taken_at` TIMESTAMP, `lat` DOUBLE, `lon` DOUBLE, `size_bytes` BIGINT, `device` STRING, `project_code` STRING, `filing_rule` STRING, `distance_m` DOUBLE, `raw_path` STRING, `seq_key` STRING | 19 |
| `documents` | `file_id` STRING, `project_code` STRING, `doc_type` STRING, `title` STRING, `version` STRING, `is_final` BOOLEAN, `file_date` DATE, `ext` STRING, `size_bytes` BIGINT, `raw_path` STRING | 19 |
| `dq_issues` | `issue_id` STRING, `issue_type` STRING, `source` STRING, `record_ref` STRING, `project_code` STRING, `detail` STRING, `detected_at` TIMESTAMP; partitioned by `job` STRING | every job, through `common.dq.write_issues` |
| `ingest_log` | `run_id` STRING, `source` STRING, `original_path` STRING, `raw_path` STRING, `seq_key` STRING, `size_bytes` BIGINT, `sha256` STRING, `business_date` DATE, `ingested_at` TIMESTAMP | 14.1 (append), 18 (photo rows) |

Value sets: `invoices.project_rule` `BOOKED` / `SINGLE_ACTIVE` / `NONE` (Task 20.1); `invoice_status.status`
upper case (Task 9); `media_files.kind` `PHOTO` / `VIDEO`; `media_files.filing_rule` `GPS` (photo filed by
position and date) / `NONE` (photo left `UNASSIGNED`) / `FOLDER` (video, filed by its project folder);
`documents.doc_type` `CONTRACT` / `PERMIT` / `GRID` / `HANDOVER` / `DRAWING` and `version` `v1` / `v2` / `final`
(drawings only), both from the file name (Task 19).

One project and one category per invoice: `invoices.category` comes from the booking, else from the supplier's
category, and every `invoice_lines` row carries its invoice's `project_code` and `category` (Task 20.1).

## 7. Data-quality issues (`dq_issues`)
`common.dq.write_issues(spark, df, job)`: df has `issue_type, source, record_ref, project_code, detail`
(`common.dq.issue_rows` builds one from Python rows); it adds `issue_id` and `detected_at`, then replaces
partition `job=<job>` only, so re-running a job never duplicates its issues and an empty df clears them. Unknown
values raise `ValueError("unknown issue_type: <x>")` / `ValueError("unknown job: <x>")`.

Jobs (`common.dq.JOBS`): `ingest`, `bank`, `finance`, `matching`, `media`.

| Issue type | Job | Raised by (task) | Meaning |
|---|---|---|---|
| `PARSE_ERROR` | bank, finance | 16, 13 | a file that can't be parsed (`record_ref` = raw path) |
| `DUPLICATE` | finance | 20 | an invoice sent twice (same supplier and number, another file); the earlier one stays |
| `MISSING_VS` | finance | 20 | an invoice without a variabilní symbol in the ISDOC and the booking |
| `NO_PROJECT` | finance | 20 | no project rule matched and the invoice has no booking at all (`source` `isdoc`), or a booked cost without project (`source` `accounting`) |
| `OVERRUN` | finance | 20 | a category spent more than 115% of its budget line |
| `UNMATCHED_PAYMENT` | matching | 25.1 | a debit matching no invoice; `detail` names a suggested invoice when one fits |
| `ORDER_NOT_CLEARED` | matching | 25.1 | a KPC payment order that no bank debit cleared |
| `NO_GPS` | media | 19 | a photo without GPS position (`project_code` NULL) |
| `UNASSIGNED_PHOTO` | media | 19 | a photo with GPS but no project site in reach on its date (`project_code` = the project whose site centre is nearest; the photo itself stays `UNASSIGNED`) |
| `WRONG_VERSION` | media | 19 | a project's final drawing is older than a numbered version |

## 8. Warehouse and catalogue
**Hive warehouse `fve_dw`** (`config.DW_DB`; EXTERNAL ORC at `<LAKE_DW>/<table>`; DDL Task 10, loads Task 26).
Names as on the ClickUp guide page; the columns below are final (Task 10.1 design in `warehouse/design/`,
reviewed in Task 15.1 on 11 Nov). Types: keys, years, months, days, `quarter` and `line_no` INT; amounts
DECIMAL(14,2), `mwp` DECIMAL(5,2); `has_battery` BOOLEAN; `construction_start`/`construction_end`/`full_date`
DATE; `days_late` INT; `cleared` TINYINT; everything else STRING. `iso_week` is the ISO week-year and week as
`YYYY-Www` (e.g. `2026-W45`, the same form as the Money S3 export week).

| Table | Columns | Partitioned by |
|---|---|---|
| `dim_project` | project_key INT, project_code, name, town, region, mwp, has_battery, contract_value, status, signed_year INT, construction_start, construction_end | - |
| `dim_supplier` | supplier_key INT, ico, name, main_category | - |
| `dim_cost_category` | category_key INT, category_code, category_name, group_name | - |
| `dim_date` | date_key INT (yyyyMMdd), full_date, day, month, month_name, quarter, year, iso_week | - |
| `dim_bank_account` | account_key INT, bank, bank_name, account, bank_code, currency | - |
| `fact_budget_line` | project_key, category_key, date_key (signed date), budget_amount | signed_year |
| `fact_invoice_line` | invoice_id, line_no, project_key, supplier_key, category_key, issue_date_key, due_date_key, amount_net, vat_amount, amount_gross, payment_status, days_late | issue_year |
| `fact_payment` | tx_id, account_key, date_key (value date), supplier_key, invoice_id, project_key, amount (positive = paid out), days_late | pay_year, pay_month |
| `fact_payment_order` | order_id, account_key, order_date_key, due_date_key, supplier_key, invoice_id, project_key, amount, cleared TINYINT | order_year |

Surrogate keys `ROW_NUMBER() OVER (ORDER BY <natural key>)`; key `-1` = the `UNKNOWN` row of `dim_project` and
`dim_supplier`; `dim_date` covers 2016-01-01 to 2026-12-31; `fact_payment` holds debits only.
`fact_invoice_line.payment_status` and `days_late` are the invoice's `invoice_status` values, the same on every
line of an invoice. `fact_payment.invoice_id` is NULL for a debit matching no invoice.
`fact_payment_order.cleared` is 1 for a matched order a bank debit cleared, 0 for one no debit cleared (the
`ORDER_NOT_CLEARED` orders) and NULL for an order matching no invoice. As an invoice has one project and one
category (section 6), a payment matched to it belongs to that project and category; no allocation across
categories is needed.

**HBase `media_catalog`** (`config.HBASE_TABLE`, Thrift at `config.HBASE_HOST:HBASE_PORT`; design Task 12, load
Task 19): row key `<project_code>#<KIND>#<yyyyMMddHHmmss>#<file_id>`, KIND `PHOTO`, `VIDEO`, `DOC`, `DRAWING`;
unfiled items under project `UNASSIGNED`. The key time is `taken_at` (UTC) for photos; videos, documents and
drawings only have a date (the date in the video's name, `file_date`) and are keyed at 00:00:00 of it; a
photo whose EXIF has no capture time is keyed at `19700101000000`, so it sorts first. Families:
`meta` (taken_at, lat, lon, size_bytes, device, original_name, ext, filing_rule), `loc` (raw_path, seq_key), `doc`
(doc_type, version, is_final, title, file_date), `thumb` (`jpg` = 96x72 JPEG thumbnail of photos). Values are
UTF-8 strings written by `hbase.catalogue.cells` (formats in `hbase/schema.md`); `filing_rule` and `doc_type`
hold the codes of section 6.

## 9. Pipeline steps (module map)
Each step is a function `run(spark) -> dict[str, int]` (row or file counts by name), called in this order by
`run_pipeline.py` (Task 21).

| Step | Function | Reads | Writes | Task |
|---|---|---|---|---|
| collect | `ingest.run` | `sources/` | `/lake/raw`, `ingest_log`, snapshot | 14.1, 18 |
| bank | `processing.bank.run` | raw `bank_gpc`, `bank_sta`, `bank_txt`, `kpc` | `bank_transactions`, `bank_tx_details`, `payment_orders`, issues `bank` | 16 |
| finance | `processing.finance.run` | raw `master`, `budgets`, `isdoc`, `invoice_pdf`, `accounting` | `projects`, `suppliers`, `budget_lines`, `invoices`, `invoice_lines`, `booked_costs`, issues `finance` | 13, 20 |
| matching | `processing.matching.job.run` | `invoices`, `suppliers`, `payment_orders`, `bank_transactions` | `invoice_status`, issues `matching` | 25.1 |
| media | `processing.media.run` | `ingest_log` (photos, video, docs), SequenceFiles, `projects` | `media_files`, `documents`, issues `media` | 19 |
| warehouse | `warehouse.etl.run.run` | clean tables | `fve_dw.*` | 26 |
| catalogue | `hbase.load.run` | `media_files`, `documents`, SequenceFiles | HBase `media_catalog` | 19 |

Shared helpers (use these, don't write your own): `common.config`, `common.schemas`, `common.tables`
(`create_clean_tables`, `write_table`, `read_table`), `common.spark.get_spark(app_name, master=None, hive=True)`,
`common.projects` (`load_projects`, `active_on`), `common.dq` (`issue_rows`, `write_issues`), `common.hdfs` and
`common.lake` (signatures fixed here, implemented in Task 14.1), `warehouse/sql.py` (Task 10).

The 10x dataset: `FVE_DATASET=x10` switches every name above (`sources_x10/`, `out_x10/`, `/bench/x10/lake`,
`fve_clean_x10`, `fve_dw_x10`); any other value is an error.
