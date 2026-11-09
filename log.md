# Log

One entry per merged task (or part with its own checkpoint), newest first:

    ### <date> - Task N: short name (your name)
    - Merged: what is now in integration
    - Checked: which tests / validation steps ran

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

