-- Experiment E5: Partition pruning comparison.
-- Run against DW_DB=fve_dw_x10 after warehouse loading.

-- Create an unpartitioned copy of the invoice fact table.
DROP TABLE IF EXISTS ${DW_DB}.fact_invoice_line_flat;

CREATE TABLE ${DW_DB}.fact_invoice_line_flat
STORED AS ORC
AS
SELECT *
FROM ${DW_DB}.fact_invoice_line;

-- Query A: Partitioned invoice fact table.
SELECT COUNT(*), SUM(amount_net)
FROM ${DW_DB}.fact_invoice_line
WHERE issue_year = 2025;

-- Query B: Unpartitioned invoice fact table.
SELECT COUNT(*), SUM(amount_net)
FROM ${DW_DB}.fact_invoice_line_flat
WHERE issue_year = 2025;

-- Explain partitioned query.
EXPLAIN EXTENDED
SELECT COUNT(*), SUM(amount_net)
FROM ${DW_DB}.fact_invoice_line
WHERE issue_year = 2025;

-- Explain unpartitioned query.
EXPLAIN EXTENDED
SELECT COUNT(*), SUM(amount_net)
FROM ${DW_DB}.fact_invoice_line_flat
WHERE issue_year = 2025;
