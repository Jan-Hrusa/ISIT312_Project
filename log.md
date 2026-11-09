# Log

One entry per merged task (or part with its own checkpoint), newest first:

    ### <date> - Task N: short name (your name)
    - Merged: what is now in integration
    - Checked: which tests / validation steps ran

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

