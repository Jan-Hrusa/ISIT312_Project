-- Overdue invoices by supplier (Faktury po splatnosti), Task 25: the queries of the Zeppelin note
-- `overdue_by_supplier`; read with warehouse.sql.named_queries (supplier_invoices needs supplier=...).
-- Counts OVERDUE invoices only: a PARTLY_PAID invoice is not due yet. HiveQL that is also valid Spark SQL.

-- name: overdue_by_supplier
-- Supplier, number of overdue invoices, open amount (gross - paid), oldest due date, average days late.
SELECT
    s.name AS supplier,
    s.ico AS ico,
    COUNT(*) AS overdue_invoices,
    SUM(v.total_gross - st.paid_amount) AS open_amount,
    MIN(v.due_date) AS oldest_due_date,
    ROUND(AVG(st.days_late), 1) AS avg_days_late
FROM ${CLEAN_DB}.invoice_status st
JOIN ${CLEAN_DB}.invoices v
    ON v.invoice_id = st.invoice_id
LEFT JOIN ${CLEAN_DB}.suppliers s
    ON s.ico = v.supplier_ico
WHERE st.status = 'OVERDUE'
GROUP BY s.name, s.ico
ORDER BY open_amount DESC, supplier;

-- name: supplier_invoices
-- One supplier's invoices (name or IČO from the form), newest due date first.
SELECT
    v.invoice_id AS invoice_id,
    v.number AS number,
    v.issue_date AS issue_date,
    v.due_date AS due_date,
    v.total_gross AS total_gross,
    st.status AS status,
    st.paid_amount AS paid_amount,
    v.total_gross - st.paid_amount AS open_amount,
    st.paid_date AS paid_date,
    st.days_late AS days_late,
    v.project_code AS project_code
FROM ${CLEAN_DB}.invoices v
JOIN ${CLEAN_DB}.suppliers s
    ON s.ico = v.supplier_ico
LEFT JOIN ${CLEAN_DB}.invoice_status st
    ON st.invoice_id = v.invoice_id
WHERE s.name = '${supplier}' OR s.ico = '${supplier}'
ORDER BY due_date DESC, invoice_id;
