# AGENTS.md

Rules for AI coding agents working in this repository. They apply to every session, every task and every agent.
If anything here conflicts with a request, stop and ask the person you work for.

## 1. The project in brief
A data lake for a Czech solar-farm construction company (ISIT312 Big Data Management group project, UOWD, 10
members, led by Jan). Sources (bank statements, invoices, budgets, accounting exports, photos, documents) land
unchanged in an HDFS raw zone; Spark jobs parse them into an ORC clean zone with one project code; a Hive warehouse
and an HBase catalogue serve Zeppelin dashboards and search. Stack: HDFS, YARN, MapReduce, Hive, Spark (PySpark
3.5), HBase, Zeppelin - all in Docker (`docker/`).

## 2. Where the information is
| What | Where | Note |
|---|---|---|
| Team rules, shared decisions, architecture, timeline | The ClickUp guide page "312 project" (the main task description) | You can't open ClickUp. Ask the member to paste the whole page before you start. |
| **Your task** (the spec: parts, files, tests, validation, "done when") | The member's ClickUp task | Ask the member to paste the full task description. It is the source of truth for the work. |
| Project and company description | Team Google Drive folder: *00 Start here*, *02 Project description*, *01 Company description* | Not in the repo on purpose. Ask the member to paste 00 and 02 (01 when the task touches the company's data). |
| Shared names: paths, tables, columns, codes | `docs/contracts.md` | Binding. Use these names exactly. |
| File formats (GPC, STA, KPC, ISDOC, MT940) | `docs/data-formats.md` | Links to the official specs. |
| Folder layout and who owns what | `README.md` | |
| Docker stack: services, commands, ports | `docker/README.md` | |
| What has been merged so far | `log.md`, `git log origin/integration` | |

Never invent requirements. If the task description is missing, unclear or contradicts `docs/contracts.md`, stop
and ask the member; they ask Jan. Don't guess and don't "improve" the scope.

## 3. Before you change anything
1. Read, in this order and in full, before you plan anything:
   1. the ClickUp guide page "312 project" (the main task description);
   2. then the description of the task you are working on (Task N or N.x);
   3. then the Drive documents *00 Start here* and *02 Project description* (*01 Company description* when
      relevant);
   4. then `README.md` and `docs/contracts.md`.

   If the member hasn't pasted the first three, ask for them; don't start from the task description alone.
2. Check the branch: `git status` and `git branch --show-current`. Work only on the member's own branch (their first
   name, lower case). If it doesn't exist yet: `git fetch origin` then `git switch -c <name> origin/integration`.
3. Bring it up to date: `git fetch origin` then `git rebase origin/integration`.
4. Read the existing files you will touch, their callers and their tests.
5. For anything bigger than a small fix, tell the member your plan in a few lines first.

## 4. Environment and commands
Everything runs in the Docker stack (`docker/README.md`); the member's laptop has only Docker Desktop and Git.
- Start it in `docker/`: `docker compose --profile core up -d` (add `--profile yarn` for MapReduce and Spark or
  Hive on YARN), then `./check.sh` must print only `OK` lines.
- Run every project command in the `client` container (Python 3.10, Spark 3.5.9, the repo at `/repo`):
  `docker compose exec client <command>`, or open a shell there with `docker compose exec client bash`. Don't run
  project code on the host; a host virtual environment is only for editor completion.
- Tests: `pytest -m "not integration"` (unit tests: the fixtures in `tests/conftest.py` never reach the stack's
  services), `pytest tests/<area>` (yours), `pytest -m integration` after a full pipeline run. Lint: `ruff check .`
  Format: `ruff format .` (check only: `ruff format --check .`).
- Hive: `docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000 -n hive`. HDFS: `hdfs dfs ...` in
  the client. Validation steps run on the stack.
- Generated data goes to `sources/`, `sources_x10/` and `out/`; these are git-ignored and never committed.

## 5. Coding rules
- **Stay in your area.** Change only the folders your task names (see the README table). A change in a shared file
  (`common/`, `docs/contracts.md`, `requirements.txt`, `docker/`) is proposed in the PR description with the reason.
- **Use the shared helpers in `common/`** (`config.py` for every path and setting, `spark.py` for the Spark session,
  `tables.py` to create, write and read clean tables, `projects.py` for project codes, `dq.py` for data-quality
  results). Never hard-code paths or write your own version of a helper.
- **Use the names from `docs/contracts.md`** for folders, files, tables, columns and codes, exactly.
- **Lake jobs use PySpark** (DataFrames / Spark SQL); pandas only in generators and small local tools. Warehouse
  DDL, loads and queries are HiveQL files in `warehouse/`.
- **Generators are deterministic:** a fixed default seed and a `--seed` option, so everyone gets the same data.
- **Tests:** every new function or job gets tests in `tests/<area>/`, using the test names the task lists. Tests must
  pass on a clean checkout.
- Match the surrounding code: naming, structure, error handling, comment style. Small, focused changes; no
  drive-by refactors, renames or reformatting of other people's files.
- Comments explain why, not what. No commented-out code, no placeholders or TODOs standing in for the work.
- New dependency only when clearly needed: add it to `requirements.txt` with a version range and say why in the PR.
- **No real company data, no company name, no personal data, no secrets** in code, data, tests, commits or
  screenshots. All data is synthetic.

## 6. Verify before you say it works
- Run the tests, `ruff check .` and `ruff format --check .` in the client container; all must pass.
- Run the task's validation steps on the Docker stack and capture the screenshots the task asks for.
- Report only what actually ran and what it printed. If something could not be run (no stack, missing data), say
  so plainly; never claim a result you did not see.

## 7. Git and pull request workflow
| Branch | Purpose |
|---|---|
| `main` | Final version only. Jan merges `integration` into it once, on Mon 23 Nov after the final review, tagged `v1.0`. |
| `integration` | Default branch. All development is merged here, by Jan, through approved PRs. |
| `<first name>` | The member's own branch, created from `integration`. All work happens here. |

1. **Commit** small, working steps: `[T<task number>] short message`, e.g. `[T16] parse GPC 075 records`.
2. **Before the PR:** rebase on `origin/integration`, re-run the checks (section 6), add a 3-line entry at the top
   of `log.md` (date, task, what was merged, which checks ran).
3. **Push** the member's branch: `git push -u origin <name>` (after a rebase: `git push --force-with-lease`, own
   branch only).
4. **Open the PR into `integration`**, never into `main`:
   `gh pr create --base integration --title "[CU-<task id>] Task N: short name"` - the title exactly as in the
   ClickUp task; fill in every section of the PR template, with the screenshots.
5. **Right after the PR is created, the member must** (you can't do these; print the PR link and remind them):
   - post the PR link as a **comment on the ClickUp task** they have just done;
   - send to the **WhatsApp group**, exactly: `Task X completed and a PR created` (X = the task number).
6. **Review:** Jan approves and merges. If he requests changes, fix them on the same branch and push; the PR updates
   itself. Never merge a PR yourself.

**Never:**
- push, commit or merge to `integration` or `main` directly, or open a PR into `main`;
- force-push anything except the member's own branch, or rewrite the history of `integration` or `main`;
- commit generated data, `.venv`, credentials or `.env` files;
- edit, move or delete other members' files without the member agreeing (shared files: see section 5);
- delete branches, tags or files you didn't create, or run destructive commands (`git reset --hard`, `git clean`,
  `rm -rf`, `hdfs dfs -rm -r` on shared paths) without asking first.

## 8. Done means
- the task's "done when" list is complete;
- tests and lint pass, validation steps done, screenshots saved;
- PR open into `integration` with the right title and template;
- the member has posted the PR link in ClickUp and the WhatsApp message;
- the task is finished only when Jan has merged the PR.
