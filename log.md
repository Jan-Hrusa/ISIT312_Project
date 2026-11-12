# Log

One entry per merged task (or part with its own checkpoint), newest first:

    ### <date> - Task N: short name (your name)
    - Merged: what is now in integration
    - Checked: which tests / validation steps ran

### 2026-11-12 - Task 6.1: Bank sample files (Obaid)
- Ready for review: GPC, STA, KPC and TXT format notes and synthetic fixtures, business dates and fixture test.
- Checked: record widths, encodings, balances, invoice-to-order correspondence and fixture paths verified directly. Docker pytest and Ruff pending due to Docker API access denial in this session.
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

