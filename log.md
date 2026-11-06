# Log

One entry per merged task (or part with its own checkpoint), newest first:

    ### <date> - Task N: short name (your name)
    - Merged: what is now in integration
    - Checked: which tests / validation steps ran

### 2026-11-06 - Task 3: Docker starter stack (Jan)
- Merged: docker/ (stack and hive images, compose profiles core and yarn, conf, check.sh, README); README Setup, AGENTS.md section 4, pyproject (Python 3.10), requirements (pyspark==3.5.9, pyhive), .gitattributes
- Checked: check.sh all 6 OK on fresh volumes (core + yarn); pytest 21 passed and ruff in the client container; namenode 1 live datanode, yarn 1 active node, data kept after down/up

### 2026-11-05 - Task 2: Architecture freeze and data contracts (Jan)
- Merged: docs/contracts.md; common/ config, schemas, tables, spark, projects, dq (hdfs, lake as signatures for 14.1); tests/conftest.py fixtures, tests/fixtures/make_sources.py
- Checked: pytest (21 passed, no stack), ruff check, ruff format --check; Validate (beeline on the stack) after Task 3

### 2026-11-05 - Task 1: AI agent reading order (Jan)
- Merged: AGENTS.md sections 2 and 3: agents read the ClickUp guide page, then the task, then Drive 00 and 02, then README and contracts
- Checked: docs only; no code changed

