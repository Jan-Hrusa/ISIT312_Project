-- name: v4_supplier_invoices
-- Invoice-level payment follow-up for one project and supplier.

WITH invoice_totals AS (
    SELECT
        invoice_id,
        SUM(amount_gross) AS gross_amount,
        MAX(payment_status) AS payment_status,
        MAX(days_late) AS days_late,
        MAX(issue_date_key) AS issue_date_key,
        MAX(due_date_key) AS due_date_key
    FROM ${DW_DB}.fact_invoice_line
    WHERE project_key = (
        SELECT project_key
        FROM ${DW_DB}.dim_project
        WHERE project_code = '${project}'
    )
      AND supplier_key = (
        SELECT supplier_key
        FROM ${DW_DB}.dim_supplier
        WHERE ico = '${supplier}'
           OR name = '${supplier}'
    )
    GROUP BY invoice_id
)
SELECT
    invoice_id,
    REGEXP_EXTRACT(invoice_id, '^[^-]+-(.*)$', 1) AS invoice_number,
    issue_date.full_date AS issue_date,
    due_date.full_date AS due_date,
    i.gross_amount AS gross_amount,
    i.payment_status AS payment_status,
    i.days_late AS days_late
FROM invoice_totals i
LEFT JOIN ${DW_DB}.dim_date issue_date
    ON i.issue_date_key = issue_date.date_key
LEFT JOIN ${DW_DB}.dim_date due_date
    ON i.due_date_key = due_date.date_key
ORDER BY
    CASE
        WHEN i.payment_status IN ('OVERDUE', 'UNPAID') THEN 1
        WHEN i.payment_status = 'PARTLY_PAID' THEN 2
        ELSE 3
    END,
    due_date ASC,
    invoice_id;
