-- "To fix" list (K vyřešení), Task 25: everything the lake could not resolve on its own, from the clean zone.
-- One query per paragraph of the Zeppelin note `to_fix`, in the same order; read with warehouse.sql.named_queries.
-- HiveQL that is also valid Spark SQL. In Zeppelin the database is written out as fve_clean.

-- name: issue_counts
-- 1. Issues per type and job (bar chart).
SELECT
    issue_type,
    job,
    COUNT(*) AS issues
FROM ${CLEAN_DB}.dq_issues
GROUP BY issue_type, job
ORDER BY issues DESC, issue_type, job;

-- name: unmatched_payments
-- 2. Debits that paid no invoice by VS, with the invoice the matching job suggests (from `detail`).
SELECT
    t.value_date,
    t.bank,
    i.record_ref AS tx_id,
    -t.amount AS amount,
    t.counterparty_account,
    t.counterparty_bank_code,
    t.vs,
    NULLIF(regexp_extract(i.detail, 'suggested match: ([^ ]+)', 1), '') AS suggested_invoice,
    i.project_code,
    i.detail
FROM ${CLEAN_DB}.dq_issues i
LEFT JOIN ${CLEAN_DB}.bank_transactions t
    ON t.tx_id = i.record_ref
WHERE i.issue_type = 'UNMATCHED_PAYMENT'
ORDER BY value_date, tx_id;

-- name: no_project
-- 3. Invoices (`isdoc`) and booked costs (`accounting`) without a project code.
SELECT
    i.source,
    i.record_ref,
    s.name AS supplier,
    COALESCE(v.issue_date, b.issue_date) AS issue_date,
    COALESCE(v.total_gross, b.amount_gross) AS amount_gross,
    i.detail
FROM ${CLEAN_DB}.dq_issues i
LEFT JOIN ${CLEAN_DB}.invoices v
    ON i.source = 'isdoc' AND v.invoice_id = i.record_ref
LEFT JOIN (
    SELECT
        doc_ref,
        MIN(supplier_ico) AS supplier_ico,
        MIN(issue_date) AS issue_date,
        SUM(amount_gross) AS amount_gross
    FROM ${CLEAN_DB}.booked_costs
    GROUP BY doc_ref
) b
    ON i.source = 'accounting' AND b.doc_ref = i.record_ref
LEFT JOIN ${CLEAN_DB}.suppliers s
    ON s.ico = COALESCE(v.supplier_ico, b.supplier_ico)
WHERE i.issue_type = 'NO_PROJECT'
ORDER BY source, issue_date, record_ref;

-- name: orders_not_cleared
-- 4. Payment orders (KPC) that no bank debit cleared, with the invoice they were for (from `detail`).
SELECT
    o.order_date,
    o.due_date,
    o.bank,
    i.record_ref AS order_id,
    o.amount,
    o.counterparty_account,
    o.counterparty_bank_code,
    o.vs,
    NULLIF(regexp_extract(i.detail, 'for invoice ([^ ]+)', 1), '') AS invoice_id,
    i.project_code
FROM ${CLEAN_DB}.dq_issues i
LEFT JOIN ${CLEAN_DB}.payment_orders o
    ON o.order_id = i.record_ref
WHERE i.issue_type = 'ORDER_NOT_CLEARED'
ORDER BY due_date, order_id;

-- name: photos
-- 5. Photos without a GPS position (NO_GPS) and photos outside every site (UNASSIGNED_PHOTO; project_code is
-- the project whose site centre is nearest). UNASSIGNED_PHOTO first: Zeppelin truncates long results (100 KB),
-- and NO_GPS (about 3,000 photos) would push the photos with a nearest project out of view.
SELECT
    i.issue_type,
    m.original_name,
    m.taken_at,
    m.lat,
    m.lon,
    i.project_code AS nearest_project,
    i.detail
FROM ${CLEAN_DB}.dq_issues i
LEFT JOIN ${CLEAN_DB}.media_files m
    ON m.file_id = i.record_ref
WHERE i.issue_type IN ('NO_GPS', 'UNASSIGNED_PHOTO')
ORDER BY issue_type DESC, taken_at, original_name;

-- name: wrong_versions
-- 6. Projects whose final drawing is older than a numbered version.
SELECT
    project_code,
    record_ref AS drawing,
    detail
FROM ${CLEAN_DB}.dq_issues
WHERE issue_type = 'WRONG_VERSION'
ORDER BY project_code;

-- name: duplicates
-- 7. Invoices sent twice: the kept invoice and the file of the dropped copy.
SELECT
    i.record_ref AS invoice_id,
    s.name AS supplier,
    v.number,
    v.total_gross,
    v.source_file AS kept_file,
    i.detail AS dropped_file,
    i.project_code
FROM ${CLEAN_DB}.dq_issues i
LEFT JOIN ${CLEAN_DB}.invoices v
    ON v.invoice_id = i.record_ref
LEFT JOIN ${CLEAN_DB}.suppliers s
    ON s.ico = v.supplier_ico
WHERE i.issue_type = 'DUPLICATE'
ORDER BY supplier, invoice_id;

-- name: parse_errors
-- 8. Files that failed to parse (record_ref = the raw path).
SELECT
    job,
    source,
    record_ref AS raw_path,
    detail
FROM ${CLEAN_DB}.dq_issues
WHERE issue_type = 'PARSE_ERROR'
ORDER BY job, raw_path;
