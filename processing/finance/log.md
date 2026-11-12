### 2026-11-12 – Task 13: Finance parsers 
- Implemented finance parsers (`master.py`, `budgets.py`, `isdoc.py`, `invoice_pdf.py`, `money_export.py`) and `processing.finance.run(spark, inputs=None)` into `fve_clean`.
- Verified all 8 unit tests in `tests/processing/test_finance.py` and validated `SELECT COUNT(*) FROM fve_clean.invoices` (= 4) on the Docker stack.
