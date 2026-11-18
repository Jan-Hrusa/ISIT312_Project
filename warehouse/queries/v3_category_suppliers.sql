-- name: v3_category_suppliers
-- Supplier breakdown for one project and cost category.
-- Payments are aggregated by invoice before joining to invoice lines.

WITH invoice_totals AS (
    SELECT
        invoice_id,
        supplier_key,
        SUM(amount_gross) AS invoiced
    FROM ${DW_DB}.fact_invoice_line
    WHERE project_key = (
        SELECT project_key
        FROM ${DW_DB}.dim_project
        WHERE project_code = '${project}'
    )
      AND category_key = (
        SELECT category_key
        FROM ${DW_DB}.dim_cost_category
        WHERE category_code = '${category}'
    )
    GROUP BY invoice_id, supplier_key
),
payments_by_invoice AS (
    SELECT invoice_id, SUM(amount) AS paid
    FROM ${DW_DB}.fact_payment
    GROUP BY invoice_id
),
supplier_totals AS (
    SELECT
        i.supplier_key,
        SUM(i.invoiced) AS invoiced,
        SUM(COALESCE(p.paid, 0)) AS paid,
        SUM(i.invoiced - COALESCE(p.paid, 0)) AS open
    FROM invoice_totals i
    LEFT JOIN payments_by_invoice p
        ON i.invoice_id = p.invoice_id
    GROUP BY i.supplier_key
)
SELECT
    s.name AS supplier,
    s.ico AS ico,
    t.invoiced AS invoiced,
    t.paid AS paid,
    t.open AS open
FROM supplier_totals t
JOIN ${DW_DB}.dim_supplier s
    ON t.supplier_key = s.supplier_key
ORDER BY t.invoiced DESC, supplier;
