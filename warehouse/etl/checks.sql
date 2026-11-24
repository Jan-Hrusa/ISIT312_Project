-- Task 26: Warehouse validation checks

-- name: invoice_amount_check
SELECT
    'invoice_amount_check' AS check_name,
    COALESCE(dw.total_amount, 0) = COALESCE(src.total_amount, 0) AS ok,
    CONCAT(
        'warehouse=', CAST(COALESCE(dw.total_amount, 0) AS STRING),
        ', clean=', CAST(COALESCE(src.total_amount, 0) AS STRING)
    ) AS detail
FROM
    (SELECT SUM(amount_net) AS total_amount
     FROM ${DW_DB}.fact_invoice_line) dw
CROSS JOIN
    (SELECT SUM(amount_net) AS total_amount
     FROM ${CLEAN_DB}.invoice_lines) src;

-- name: budget_amount_check
SELECT
    'budget_amount_check' AS check_name,
    COALESCE(dw.total_amount, 0) = COALESCE(src.total_amount, 0) AS ok,
    CONCAT(
        'warehouse=', CAST(COALESCE(dw.total_amount, 0) AS STRING),
        ', clean=', CAST(COALESCE(src.total_amount, 0) AS STRING)
    ) AS detail
FROM
    (SELECT SUM(budget_amount) AS total_amount
     FROM ${DW_DB}.fact_budget_line) dw
CROSS JOIN
    (SELECT SUM(b.amount) AS total_amount
     FROM ${CLEAN_DB}.budget_lines b
     JOIN ${CLEAN_DB}.projects p
       ON b.project_code = p.project_code
     WHERE p.signed_date IS NOT NULL
       AND p.status <> 'NOT_SIGNED') src;

-- name: payment_count_check
SELECT
    'payment_count_check' AS check_name,
    dw.row_count = src.row_count AS ok,
    CONCAT(
        'warehouse=', CAST(dw.row_count AS STRING),
        ', clean_debits=', CAST(src.row_count AS STRING)
    ) AS detail
FROM
    (SELECT COUNT(*) AS row_count
     FROM ${DW_DB}.fact_payment) dw
CROSS JOIN
    (SELECT COUNT(*) AS row_count
     FROM ${CLEAN_DB}.bank_transactions
     WHERE amount < 0) src;

-- name: fact_key_integrity_check
WITH invalid_keys AS (
    SELECT COUNT(*) AS n
    FROM ${DW_DB}.fact_budget_line
    WHERE project_key IS NULL OR category_key IS NULL OR date_key IS NULL

    UNION ALL

    SELECT COUNT(*)
    FROM ${DW_DB}.fact_invoice_line
    WHERE project_key IS NULL OR supplier_key IS NULL
       OR category_key IS NULL OR issue_date_key IS NULL
       OR due_date_key IS NULL

    UNION ALL

    SELECT COUNT(*)
    FROM ${DW_DB}.fact_payment
    WHERE account_key IS NULL OR date_key IS NULL
       OR supplier_key IS NULL OR project_key IS NULL

    UNION ALL

    SELECT COUNT(*)
    FROM ${DW_DB}.fact_payment_order
    WHERE account_key IS NULL OR order_date_key IS NULL
       OR supplier_key IS NULL OR project_key IS NULL
),
invalid_dates AS (
    SELECT date_key FROM ${DW_DB}.fact_budget_line
    UNION ALL
    SELECT issue_date_key FROM ${DW_DB}.fact_invoice_line
    UNION ALL
    SELECT due_date_key FROM ${DW_DB}.fact_invoice_line
    UNION ALL
    SELECT date_key FROM ${DW_DB}.fact_payment
    UNION ALL
    SELECT order_date_key FROM ${DW_DB}.fact_payment_order
    UNION ALL
    SELECT due_date_key FROM ${DW_DB}.fact_payment_order
),
missing_dates AS (
    SELECT COUNT(*) AS n
    FROM invalid_dates d
    LEFT JOIN ${DW_DB}.dim_date dd ON d.date_key = dd.date_key
    WHERE dd.date_key IS NULL
)
SELECT
    'fact_key_integrity_check' AS check_name,
    (SELECT SUM(n) FROM invalid_keys) = 0
        AND (SELECT n FROM missing_dates) = 0 AS ok,
    CONCAT(
        'null_keys=', CAST((SELECT SUM(n) FROM invalid_keys) AS STRING),
        ', missing_dates=', CAST((SELECT n FROM missing_dates) AS STRING)
    ) AS detail;

-- name: payment_tx_unique_check
SELECT
    'payment_tx_unique_check' AS check_name,
    COUNT(*) = 0 AS ok,
    CONCAT(
        'duplicate_tx_ids=', CAST(COUNT(*) AS STRING)
    ) AS detail
FROM (
    SELECT tx_id
    FROM ${DW_DB}.fact_payment
    GROUP BY tx_id
    HAVING COUNT(*) > 1
) duplicates;
