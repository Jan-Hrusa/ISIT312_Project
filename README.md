# ISIT312 Project – One Place per Project

A data lake for a Czech solar-farm construction company: every invoice, bank statement, budget, site photo and
project document lands unchanged in one place, gets one project code, and gives management a daily
cost-vs-budget overview per project. Group project for ISIT312 Big Data Management (UOWD, Autumn 2026).

- **What we build and why:** [docs/project-description.md](docs/project-description.md)
- **The company:** [docs/company.md](docs/company.md) (summary only; the interview itself is confidential)
- **File formats** (GPC, STA, KPC, ISDOC, ...): [docs/data-formats.md](docs/data-formats.md)
- **Names everyone builds against** (paths, tables, codes): `docs/contracts.md` (Task 2, from Thu 5 Nov)
- **Tasks:** ClickUp, space "ISIT312 Project", task "312 project" – read its guide page first
- **Report, slides, lessons log, screenshots:** the team Google Drive folder (link in ClickUp)

## Repository layout
| Folder | What goes there | Tasks |
|---|---|---|
| `docker/` | Docker Compose stack (HDFS, YARN, Hive, Spark, HBase, Zeppelin), `check.sh`, setup guide | 3, 8 |
| `common/` | Shared helpers: `config.py`, `spark.py`, `projects.py`, `dq.py` – use these, don't write your own | 2 |
| `generators/finance_docs/` | Projects, suppliers, budgets, ISDOC invoices + PDFs, accounting export | 5, 17 |
| `generators/bank/` | GPC, STA, TXT statements and KPC payment orders | 6 |
| `generators/media/` | Site photos (EXIF date + GPS), videos, documents, drawings | 7 |
| `ingest/` | Collection into the raw zone, ingest log, snapshots, photo packing | 14, 18 |
| `processing/bank/`, `processing/finance/`, `processing/matching/`, `processing/media/` | Spark jobs into the clean zone | 13, 16, 19, 20, 9, 25 |
| `warehouse/design/`, `warehouse/ddl/`, `warehouse/etl/`, `warehouse/queries/` | Hive warehouse: UMLet designs, DDL, loads, OLAP queries | 10, 22, 26 |
| `hbase/` | `media_catalog` table design and load | 12, 19 |
| `notebooks/` | Zeppelin notebooks (dashboard, "to fix", search) | 25, 30, 32 |
| `benchmarks/e1` ... `e5` | The five tool-comparison experiments | 23, 24, 32, 27, 31 |
| `tests/` | Tests per area (`tests/<area>/`) | all |
| `run_pipeline.py` | Runs every step in order (added in Task 21) | 21 |

`sources/`, `sources_x10/` and `out/` are generated locally and never committed.

## Setup
1. Python 3.11 or 3.12: create a virtual environment `.venv` and install `requirements.txt`.
2. Big data stack: Docker (`docker/`, from Fri 6 Nov – see `docker/README.md`) or the class BigDataVM.
3. `pytest` and `ruff check .` must pass before every pull request.

## How we work
- **Branches:** one branch per person, named after you (first name, lower case). `main` is the integration branch;
  only Jan merges into it. Never push to `main` directly.
- **At the start of every session:** fetch, switch to your branch, rebase it on `origin/main`.
- **Commits:** `[T<task number>] short message`, e.g. `[T16] parse GPC 075 records`.
- **Pull requests:** title exactly as in your ClickUp task, `[CU-<task id>] Task N: short name`; fill in the template;
  add your screenshots; add a 3-line entry to [log.md](log.md).
- **Due means merged:** open the PR at least a day before the due date.
- **Shared names** (folders, tables, columns, codes) come from `docs/contracts.md`; propose changes in your PR,
  don't change them alone.
- **No real company data** anywhere in this repository – all data is synthetic.
