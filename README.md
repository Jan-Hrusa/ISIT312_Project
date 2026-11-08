# ISIT312 Project – One Place per Project

A data lake for a Czech solar-farm construction company: every invoice, bank statement, budget, site photo and
project document lands unchanged in one place, gets one project code, and gives management a daily
cost-vs-budget overview per project. Group project for ISIT312 Big Data Management (UOWD, Autumn 2026).

- **What we build and why, and the company:** the team Google Drive folder (link on the ClickUp guide page):
  *02 Project description* and *01 Company description*. They live only there.
- **File formats** (GPC, STA, KPC, ISDOC, ...): [docs/data-formats.md](docs/data-formats.md)
- **Names everyone builds against** (paths, tables, codes): [docs/contracts.md](docs/contracts.md)
- **Tasks:** ClickUp, space "ISIT312 Project", task "312 project" – read its guide page first
- **Report, slides, lessons log, screenshots:** the same Drive folder
- **Rules for AI coding agents:** [AGENTS.md](AGENTS.md)

## Repository layout
| Folder | What goes there | Tasks |
|---|---|---|
| `docker/` | Docker Compose stack (HDFS, YARN, Hive, Spark, HBase, Zeppelin), `check.sh`, setup guide | 3, 8 |
| `common/` | Shared helpers: `config.py`, `schemas.py`, `tables.py`, `spark.py`, `projects.py`, `dq.py` (Task 2), `hdfs.py`, `lake.py` (Task 14.1) – use these, don't write your own | 2, 14.1 |
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

`sources/`, `sources_x10/`, `out/` and `out_x10/` are generated locally and never committed.

## Setup
Everything runs in Docker: install Docker Desktop (at least 6 GB of memory) and Git (on Windows also Git Bash),
nothing else. All Python, Spark, tests and tools run in the `client` container (Python 3.10, Spark 3.5.9), which
sees this repo at `/repo`. Full guide: [docker/README.md](docker/README.md).

Run every `docker compose` command in the `docker/` folder. Step by step from zero: the Drive document
*06 First-time setup*.

1. In `docker/`: build the two images once (about 15 minutes) with
   `docker compose --profile core build --build-arg APACHE_MIRROR=https://dlcdn.apache.org`, start with
   `docker compose --profile core up -d`, then `./check.sh` must print `OK hdfs`, `OK hive`, `OK spark`,
   `OK metastore`.
2. Shell in the client: `docker compose exec client bash`.
3. Before every pull request, in the client: `pytest -m "not integration"` (unit tests, no data needed; `pytest -m
   integration` after a full pipeline run), `ruff check .` and `ruff format --check .` must pass.

A virtual environment on the laptop is optional, only for your editor's code completion; don't run the code there.

## How we work
| Branch | Purpose | Who merges into it |
|---|---|---|
| `main` | Final version only. `integration` is merged into it once, on Mon 23 Nov after the final review, tagged `v1.0` | Jan |
| `integration` | Default branch; all development is merged here through pull requests | Jan, after approving the PR |
| `<first name>` (lower case) | Your own branch, created from `integration`; all your work happens here | you push to it |

1. **At the start of every session:** `git fetch origin`, switch to your branch, `git rebase origin/integration`.
   After a rebase, push with `git push --force-with-lease` (your own branch only), never `git pull`.
2. **Commits:** `[T<task number>] short message`, e.g. `[T16] parse GPC 075 records`.
3. **Before the PR:** tests, `ruff check .` and `ruff format --check .` pass; your task's validation steps are done;
   screenshots taken; a 3-line entry added to [log.md](log.md).
4. **Pull request** into `integration` (never `main`), titled exactly as in your ClickUp task
   (`[CU-<task id>] Task N: short name`), with the template filled in.
5. **Right after creating the PR:**
   - post the PR link as a **comment on the ClickUp task** you have just done;
   - send to the **WhatsApp group**: `Task X completed and a PR created` (X = your task number).
6. **Review:** Jan approves and merges into `integration`, or requests changes - fix them on the same branch and push;
   the PR updates itself. Never merge your own PR.

- **Due means merged:** open the PR at least a day before the due date.
- **Shared names** (folders, tables, columns, codes) come from `docs/contracts.md`; propose changes in your PR,
  don't change them alone.
- **No real company data** anywhere in this repository - all data is synthetic.
