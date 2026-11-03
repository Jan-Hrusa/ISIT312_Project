# Project description: "Zakázka na jednom místě" (One Place per Project)

A data lake for a Czech solar-farm construction company that brings every invoice, bank statement, budget, site photo
and project document into one place, gives management a **daily cost-vs-budget overview per project**, and files
site photos and documents to the right project automatically.

Agreed on 3 Nov 2026. The company is described in [company.md](company.md); the tasks are in ClickUp ("312 project").

---

## 1. The problem (current state, "as is")

The company: about 8 employees. It builds 8-10 solar plants a year of 1-2 MW each, plus battery storage, turnkey from permits to commissioning, with servicing as an extra. Design and surveying are
done by external firms. No IT department; everyone looks after their own computer.

| Spec point | Today | With the data lake |
|---|---|---|
| 1. How much data | ~10 years of history; 100-150 photos at the start of each project, then continuous photos through about a year of construction; ~80 bank statement files a month from 4 banks; 30-40 suppliers; offer documents of 80-90 pages. Total storage size not yet known (asked in the call-back). | All of it kept in one raw zone for the legal retention periods; volume measured on the synthetic 10-year dataset (§5.1); room to grow with more projects and monitoring data (§1.1). |
| 2. How it's collected | Banks email a GPC file daily; suppliers email invoices as ISDOC + PDF; subcontractors email PDFs and post paper; the site manager emails photos or uploads them to the Drive, often a month late. | Collected automatically every night from one company mailbox and Drive folders; nobody files anything by hand (§3). |
| 3. Where it's stored | Google Drive with the same folder structure for every project; Money S3 accounting run by an external accountant; emails kept per person, not centrally. No backup against human deletion: Google restores only 60 days, and an admin nearly deleted everything once. | HDFS raw zone, write-once, with nightly snapshots; clean zone in ORC; Hive warehouse and HBase catalogue (§5.2, §5.4). |
| 4. How it's processed | Statements imported semi-automatically; invoice-payment matching by *variabilní symbol* is semi-automatic and doesn't always work, so someone resolves the rest by hand; handover documentation assembled by hand; cost vs budget kept in a spreadsheet updated by hand every 2-3 months. | Nightly Spark jobs parse every format, match payments to invoices and file photos; cost vs budget is recalculated daily; only real exceptions reach a person, as a "to fix" list (§5.3). |
| 5. Integration | Bank → accounting through data files with a person assisting; no single project ID across systems; master data split between accounting and Drive; no project management tool. | One project code links bank, invoices, accounting, budgets, documents and photos; shared dimensions in the warehouse (§5.3, §5.4). |
| 6. Issues | Late or missing photos and documents; one wrong drawing version used; no protection against deletion; data quality depends on people. | Photos filed by GPS and date; "latest drawing" from the catalogue's version field; snapshots against deletion; data-quality checks make gaps visible (§5.2-5.5). |

**What management wants most:** "an overview of costs and budget per project; that's what I want to see first". **Constraints:** cloud is fine; it must be as simple as possible, need no maintenance and
not require hiring anyone; current spend is about 3,000 CZK a month plus ~15,000 CZK a year.

### 1.1 Why a data lake is the right solution (Aspect 1, Motivation)
1. **Variety.** Twelve approved formats: fixed-width bank files (GPC, KPC), tagged text (STA), XML (ISDOC), spreadsheets,
   office documents, and binary drawings, photos and videos. A spreadsheet or a single relational database can't hold
   all of them in their original form; a data lake stores everything as received and applies structure on read.
2. **Retention without loss.** Tax documents must be kept 10 years and payroll records 50 years;
   today the only protection is Google's 60-day restore. A write-once raw zone with snapshots keeps the
   originals for as long as the law requires.
3. **Integration across sources with no common key**. Linking bank, accounting, budgets, documents and
   photos needs a processing layer over all of them, not another isolated tool.
4. **Reprocessing.** Because the raw data is never changed, new questions (e.g. a new cost category or a better
   matching rule) can be answered over all 10 years of history by re-running a job.
5. **Growth.** More projects are planned, battery storage for grid-balancing services is being developed, and 24/7 plant monitoring is offered as a service; asked whether readings then arrive every minute or
   every five minutes, the representative agreed.
   Monitoring data is where real volume and velocity arrive; the lake already has the zones and tools to take it
   (Spark Streaming and Kafka are covered in the tool comparison, §6).
6. **Deployment fits the constraint.** "As simple as possible, nobody to maintain it" is a deployment
   requirement, not an argument against the architecture: the same zones and jobs run on a managed cloud service
   (e.g. a hosted Hadoop/Spark service next to their Google account), so the company runs nothing itself (§7).

## 2. The idea in one paragraph

Every source the company already has (bank emails, invoice emails, the accountant's export, budget spreadsheets,
site photos, Drive documents) lands **unchanged** in a raw zone of a data lake. Nightly jobs parse each format,
give every record a **single project code** (e.g. `FVE-2026-07`), match payments to invoices and file photos to
projects by GPS and date. The results feed a **Hive data warehouse** (budget vs actual, margin, cost per MWp,
overdue payments) and an **HBase catalogue** of photos and documents. Users see a dashboard, a search page and a
"to fix" list; the site manager's only change is sending photos to one address.

## 3. How data gets in (in reality vs in our demo)

Users never upload into a new app. The system collects from the places data already goes.

| Data | Reality | Demo | People's change |
|---|---|---|---|
| GPC / STA statements | A company mailbox (`data@…`) added as a second recipient in each bank; attachments collected nightly | Generator writes into `sources/mailbox/` | One-time bank setting |
| ISDOC + PDF invoices | Gmail rule forwards invoice emails to the mailbox | Generator → `sources/mailbox/` | One-time rule |
| KPC payment orders | Copy saved to a Drive folder | Generator → `sources/drive/payments/` | Small habit for the accountant |
| Money S3 export (booked costs with project code) | Accountant drops a weekly export into a Drive folder | Generator → `sources/drive/accounting/` | **The one manual step** |
| Budget per project (from the SOD) | Read from the Drive nightly | Generator → `sources/drive/budgets/` | One standard template with the project code and fixed cost categories |
| Photos, videos | Sent from the phone to `fotky@…` or camera upload into a Drive inbox folder | Generator → `sources/mailbox/photos/` | Location on in the camera |
| DOC / PDF / DWG | Read-only nightly copy of the project folders | Generator → `sources/drive/projects/` | None |

## 4. Users and what they see

| User | Sees | Demo form |
|---|---|---|
| Management | Project list with budget, spent, % spent, expected margin, traffic light; drill-down project → cost category → supplier → invoices and payment status; cost per MWp across projects; optional Monday email with overruns and overdue invoices | Zeppelin notebook with Hive queries and charts |
| Office / accountant | "To fix" list: unmatched payments, invoices without a project code, photos without a location | Zeppelin notebook |
| Anyone needing a file | Search: "FVE-2026-07, photos, before 1 Sep" → thumbnails with date and place; "latest drawing" → final version | Zeppelin notebook querying HBase |
| Site manager | Nothing new; a confirmation reply "12 photos filed to FVE-2026-07" | Not demoed |

## 5. Architecture

```
SOURCES (synthetic)        RAW ZONE (HDFS)               CLEAN ZONE (HDFS, ORC)        SERVING
mailbox: GPC, STA,  ─┐     /lake/raw/<source>/<y>/<m>/   Spark jobs (PySpark):         Hive warehouse
  ISDOC+PDF, photos  │     write-once, never             parse every format,           (fact constellation)
drive: KPC, Money S3 ├──►  overwritten; daily HDFS  ──►  assign project code,    ──►   + OLAP queries
  export, budgets,   │     snapshots; photos packed      match invoice↔payment,        → Zeppelin dashboards
  DOC/PDF/DWG        │     into SequenceFiles            file photos by GPS+date,
                    ─┘                                   data-quality checks           HBase media/doc catalogue
          Python ingest job (scheduled)                                                → search notebook
```

Course mapping: HDFS (Weeks 1-2), MapReduce (Weeks 2-3, used in the tool comparison), Hive and data warehouse
design, OLAP, physical design and ETL (Weeks 3-5), HBase (Week 6), Spark and Spark SQL (Week 7). Streaming (Weeks
8-9) is not built; it is covered in the tool comparison (decision 2026-11-03).

### 5.1 Synthetic data (stage 1)
Generated from the public format specs (ABO/GPC/KPC, MT940/STA, ISDOC) and the company's parameters from the
interview, so it looks like their data without being their data.

| Entity | Volume (10 years) |
|---|---|
| Projects | ~90 (`FVE-YYYY-NN`, town, GPS centre + radius, 1-2 MWp, battery yes/no, contract value, dates, status active / completed / not signed) |
| Suppliers | ~35 (fake IČO, bank account, category) |
| Bank accounts | 4 banks; primary bank daily statements, the others monthly; one bank exports MT940 (STA) |
| Budgets | one XLSX per project, ~10 cost categories (panels, inverters, structures, cables, earthworks, grid connection, batteries, design, survey, other) |
| Invoices | ~5,000 ISDOC XML + PDF (some PDF-only) with *variabilní symbol*, due date, lines |
| Payments | GPC/STA statements (~80 files a month), KPC payment orders; some late, partial or missing payments on purpose |
| Accounting export | weekly Money S3 CSV/XML of booked costs with project code and cost centre |
| Photos | ~1,000 per project (small JPGs with EXIF date and GPS; ~10% without GPS on purpose). *Assumption*: the interview gives 100-150 photos at the start plus continuous photos during construction, not a total; adjust once the Drive size is known |
| Videos, documents | a few short MP4s; DOC/PDF contracts and permits; dummy DWG files named v1 / v2 / final |
| TXT | bank supplementary info files |

Planted problems (overruns, late payments, unmatched payments, photos without location, a duplicate document,
a wrong drawing version) give the dashboards and the "to fix" list something real to show.

### 5.2 Ingestion and raw zone (stage 2)
- Layout: `/lake/raw/<source>/<yyyy>/<mm>/<original name>__<ingest UTC yyyyMMddHHmmss>.<ext>`; photos as daily
  SequenceFiles `/lake/raw/photos/<yyyy>/<mm>/<yyyy-MM-dd>.seq` (as fixed in the ClickUp guide page).
- **Write-once**: files are never changed or deleted; a new version gets a new name with the ingest timestamp.
- **HDFS snapshots** of `/lake/raw` every night: the protection against accidental deletion that the company lacks
  (Google's 60-day limit).
- **Small files**: thousands of photos would overload the NameNode, so each day's photos are packed into a
  SequenceFile (key = original file name, value = bytes).
- An ingest log records every file (source, size, checksum, time) so nothing is collected twice.

### 5.3 Processing and clean zone (stage 3)
Spark (PySpark) jobs, output as ORC tables in `/lake/clean/`:
1. **Parsers**: GPC (fixed-width records 074 statement / 075 transaction), STA (MT940 tags `:61:` / `:86:`), KPC
   (payment orders), TXT (the bank's supplementary information files, joined to the matching transactions),
   ISDOC XML (header and lines), Money S3 export, budget XLSX, EXIF metadata of photos and videos, document file
   names (project, type, version).
2. **Project code**: every invoice line, budget line and booked cost gets one project code (from the accounting
   export or the budget file; the rest goes to the "to fix" list).
3. **Matching**: an invoice is *ordered* when a KPC payment order with its *variabilní symbol* exists, and *paid*
   when a bank debit with the same *variabilní symbol* and amount appears in a GPC/STA statement → status unpaid /
   ordered / paid / partly paid / overdue, days to pay. Orders that never clear go to the "to fix" list.
4. **Photo filing**: a photo belongs to a project if its GPS point lies within the project's radius and its date
   is within the project's construction period; otherwise it is marked "unassigned".
5. **Data-quality checks**: duplicates, missing *variabilní symbol*, invoices without a project, unmatched
   payments, files that failed to parse. They feed the "to fix" list.

### 5.4 Serving (stage 4)
**Hive warehouse**: a fact constellation (several fact tables sharing dimensions), designed conceptually,
logically and physically as in Lab 5.

| Table | Grain / content |
|---|---|
| `fact_budget_line` | one budget amount per project × cost category |
| `fact_invoice_line` | one invoice line: amount, VAT, project, category, supplier, issue/due date |
| `fact_payment` | one bank transaction (GPC/STA, with TXT supplementary details): amount, date, account, matched invoice, days late |
| `fact_payment_order` | one KPC payment order line: amount, order date, *variabilní symbol*, matched invoice, cleared yes/no |
| `dim_project` | code, name, town, region, MWp, battery, contract value, status; hierarchy project → region |
| `dim_supplier` | IČO, name, category; hierarchy supplier → category |
| `dim_cost_category` | category → group (technology / construction / services) |
| `dim_date` | day → month → quarter → year |
| `dim_bank_account` | bank, account, currency |

Physical design: ORC, facts partitioned by year (payments by year and month), dimensions small.
Example OLAP queries: budget vs actual per project and category with `ROLLUP`; spend by category × year with
`CUBE`; cumulative spend per project over time (window `SUM … OVER`); most-overrun categories (`RANK`);
month-on-month change (`LAG`); cost per MWp across projects; overdue invoices by supplier.

**HBase catalogue** `media_catalog`: row key `<project_code>#<type>#<yyyyMMddHHmmss>#<file_id>`, so a range scan
returns "photos of a project between two dates" in order. Column families: `meta` (taken_at, lat, lon, size,
device, source), `loc` (HDFS SequenceFile path and key), `doc` (version, is_final). Unassigned items are under
the prefix `UNASSIGNED#`.

### 5.5 Use (stage 5)
Zeppelin notebooks (part of the BigDataVM stack): management dashboard, "to fix" list, media and document search.
The report describes the real-world equivalents (web dashboard such as Looker Studio, Gmail/Drive connectors).

## 6. Tool comparison (the spec's "why some tools are not appropriate", measured)

| # | Experiment | Measure | Expected point |
|---|---|---|---|
| E1 | Parse 10 years of GPC statements in MapReduce (mrjob), Spark and Hive | runtime, lines of code | Spark is the fastest to write and run for multi-step processing; MapReduce works but is verbose and slow |
| E2 | Store ~90,000 photos as loose files vs daily SequenceFiles | NameNode objects (`hdfs dfs -count`, `fsck`), ingest time | the small-files problem and its fix |
| E3 | Same question in HBase vs Hive: one project's photos in a date range, and total cost per category | latency | HBase for point and range lookups, Hive for aggregation |
| E4 | Data arrival rates (~80 statement files a month, daily batches) | arrival rate vs streaming need | Kafka / Spark Streaming not justified for this data; would fit only plant monitoring, a paid extra service today |
| E5 | Dashboard queries on MapReduce-backed Hive vs Spark | latency | batch MapReduce is unsuitable for interactive use |

E1-E3 and E5 are measurements on our build. E4 is weaker: streaming is not built (decision 2026-11-03), so E4
measures the arrival rates of the generated data and argues from them; the report says so openly.

## 7. Limitations and constraints (report section vi)
- **Deployment.** Today's volume is modest (~8 people, ~10 projects a year); the case for the data lake rests on
  variety, retention, integration and growth (§1.1). Because the company wants nothing to maintain, the
  recommended deployment is a managed cloud service running the same zones and jobs, not an own cluster; our build
  runs on the course stack (Docker / BigDataVM) to demonstrate it.
- The representative noted that a cost-analysis add-on for the accounting software would produce a similar
  overview. It sees only what the external accountant has booked; our design combines the contract
  budget, invoices, bank payments, documents and photos, daily.
- Data is synthetic (the company declined to provide samples); realism comes from the public format specs
  and the interview figures.
- Photo filing needs GPS on the phones; the fallback is the "unassigned" list.
- The daily overview is only as fresh as the weekly accounting export for costs not yet invoiced.
- Streaming is analysed but not built (E4).

## 8. What the company gets
A written assessment of the current setup and its risks, the target architecture, a step-by-step plan to adopt it
cheaply with the tools they already pay for, and a working demonstration on data shaped like theirs. Their
evaluation (call-back on the idea, review at the end, quotable written feedback) goes into the
report's evaluation section.

### 8.1 Evidence for the evaluation (Aspect 3)
Aspect 3 asks what *we* learned from the stakeholder, how practice compared with the lectures and labs, and the
company's opinion. Evidence is collected during the project, not reconstructed at the end:
- **Lessons log** (Google Drive, one shared document): every member adds one dated entry a week: what they did, what
  surprised them, how it compared with the lecture or lab on that tool. Jan collects it for the report.
- **Company interactions**: Jan adds notes after every call or email (date, what was presented, the company's
  reaction, quotes they allow). Sources: the interview, the call-back and the
  evaluation on 19-20 Nov.

### 8.2 Screenshot checklist (report section v)
Section v needs screenshots of the architecture, pipelines and sample jobs running on the lake. Each task's "done
when" list includes its screenshots, saved to the team Drive folder `Screenshots/<area>/`:
- HDFS: NameNode web UI with the `/lake` tree, a snapshot listing, `hdfs dfs -count` before/after SequenceFiles (E2)
- Ingestion: a run log showing files collected
- Spark: a job in the Spark UI / YARN ResourceManager UI, with its output table
- Hive: DDL of the fact and dimension tables, `SHOW PARTITIONS`, each OLAP query with its result
- HBase: `describe 'media_catalog'`, a range scan for one project and date range
- Zeppelin: the dashboard, the "to fix" list, the search notebook
- Benchmarks: a result table or chart for each of E1-E5

## 9. Mapping to the report structure (spec)
| Report section | Content from this project |
|---|---|
| i. Executive summary | Section 2 + results |
| ii. Motivation | Section 1 and 1.1 (current state, pain points, why a data lake) |
| iii. Technical requirements | Sections 3-4 (sources, users, freshness, constraints) |
| iv. Main constructs | Zones, project code, matching, fact constellation (Hive), catalogue (HBase) |
| v. Implementation | Section 5 with code, screenshots (8.2) and sample jobs; the new setup per spec point (§1 table); Section 6 results |
| vi. Limitations | Section 7 |
| vii. Conclusion | Company evaluation, lessons learned (8.1) |

## 10. Team areas
Every member builds part of the solution and writes the report sections and presents the slides for their own area.
Jan leads: data contracts, setup, pipeline runner, company contact, final report and deck.

| Area | What you work on | Main tools | ClickUp tasks |
|---|---|---|---|
| 2 – Finance data generator | Synthetic finance data: projects, suppliers, budgets, ISDOC invoices + PDFs, accountant's export; planted problems; 10x dataset | Python, XML, Excel | 5, 17, 28 |
| 3 – Bank data | Bank statements (GPC, STA) and payment orders (KPC) to the official formats; Spark parsers; experiment E1 | Python, Spark, MapReduce | 6, 16, 23 |
| 4 – Site photos and documents | Photos with GPS and dates, videos, contracts, drawing versions; SequenceFile packing; experiment E2 | Python, HDFS | 7, 18, 24 |
| 5 – Platform and raw zone | Full Docker stack; collection job and ingest log; snapshots and restore demo; experiment E4 | Docker, HDFS, Python | 8, 14, 27 |
| 6 – Finance processing | Spark parsers for invoices, budgets, export; project codes; data-quality checks | Spark, Python | 13, 20, 29 |
| 7 – Payment matching | Invoice-to-payment matching rules and job; "to fix" and overdue notebooks | Python, Spark, Zeppelin | 9, 25, 34 |
| 8 – Data warehouse | Hive warehouse design (conceptual, logical, physical), loads and checks; experiment E5 | Hive, UMLet, SQL | 10, 26, 31 |
| 9 – Management dashboard | Dashboard design, OLAP queries, Zeppelin dashboard | Hive SQL, Zeppelin | 11, 22, 30 |
| 10 – Photo filing and search | Photo filing by GPS and date, HBase catalogue, search notebook; experiment E3 | Spark, HBase, Python | 12, 19, 32 |

## 11. Risks and fallbacks
| Risk | Fallback |
|---|---|
| Docker stack with Hive + HBase + Spark takes too long | Everyone already has the BigDataVM, which has the stack |
| Spark is new this week | Parsers can run as MapReduce or Hive; E1 needs a MapReduce version anyway |
| Generators late, everyone blocked | Small hand-checked sample sets due Mon 9 Nov; full generators Wed 11 Nov |
| Scope creep | Streaming dropped; no web app (Zeppelin only) |

## 12. Key dates
| Date | Milestone |
|---|---|
| Sun 8 Nov | Kick-off, team starts |
| Mon 9 Nov | Sample files |
| Tue 10 Nov | Designs done, full Docker stack |
| Wed 11 Nov | Full synthetic dataset |
| Sat 14 Nov | Integration day |
| Wed 18 Nov | Feature freeze: everything merged, experiments run |
| Thu 19 - Fri 20 Nov | Company evaluation |
| Fri 20 Nov | Report drafts |
| Sat 21 Nov | Slides |
| Mon 23 Nov | Final review and rehearsal |
| Week 10 | Submission and presentation |
