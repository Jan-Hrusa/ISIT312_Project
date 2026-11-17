-- Task 26: Warehouse fact loads

-- Budget lines for signed projects
INSERT OVERWRITE TABLE ${DW_DB}.fact_budget_line
PARTITION (signed_year)
SELECT
    p.project_key,
    COALESCE(c.category_key, -1) AS category_key,
    CAST(date_format(pr.signed_date, 'yyyyMMdd') AS INT) AS date_key,
    b.amount AS budget_amount,
    YEAR(pr.signed_date) AS signed_year
FROM ${CLEAN_DB}.budget_lines b
JOIN ${CLEAN_DB}.projects pr
    ON b.project_code = pr.project_code
JOIN ${DW_DB}.dim_project p
    ON b.project_code = p.project_code
LEFT JOIN ${DW_DB}.dim_cost_category c
    ON b.category = c.category_code
WHERE pr.signed_date IS NOT NULL
  AND pr.status <> 'NOT_SIGNED';

-- Invoice lines with payment status
INSERT OVERWRITE TABLE ${DW_DB}.fact_invoice_line
PARTITION (issue_year)
SELECT
    l.invoice_id,
    l.line_no,
    COALESCE(p.project_key, -1) AS project_key,
    COALESCE(s.supplier_key, -1) AS supplier_key,
    COALESCE(c.category_key, -1) AS category_key,
    CAST(date_format(i.issue_date, 'yyyyMMdd') AS INT) AS issue_date_key,
    CAST(date_format(i.due_date, 'yyyyMMdd') AS INT) AS due_date_key,
    l.amount_net,
    l.vat_amount,
    CAST(l.amount_net + l.vat_amount AS DECIMAL(14,2)) AS amount_gross,
    st.status AS payment_status,
    st.days_late,
    YEAR(i.issue_date) AS issue_year
FROM ${CLEAN_DB}.invoice_lines l
JOIN ${CLEAN_DB}.invoices i
    ON l.invoice_id = i.invoice_id
LEFT JOIN ${CLEAN_DB}.invoice_status st
    ON l.invoice_id = st.invoice_id
LEFT JOIN ${DW_DB}.dim_project p
    ON COALESCE(l.project_code, i.project_code) = p.project_code
LEFT JOIN ${DW_DB}.dim_supplier s
    ON i.supplier_ico = s.ico
LEFT JOIN ${DW_DB}.dim_cost_category c
    ON COALESCE(l.category, i.category) = c.category_code;

-- Debit transactions converted to positive payment outflows
INSERT OVERWRITE TABLE ${DW_DB}.fact_payment
PARTITION (pay_year, pay_month)
SELECT
    t.tx_id,
    COALESCE(a.account_key, -1) AS account_key,
    CAST(date_format(t.value_date, 'yyyyMMdd') AS INT) AS date_key,
    COALESCE(s.supplier_key, -1) AS supplier_key,
    st.invoice_id,
    COALESCE(p.project_key, -1) AS project_key,
    CAST(-t.amount AS DECIMAL(14,2)) AS amount,
    st.days_late,
    YEAR(t.value_date) AS pay_year,
    MONTH(t.value_date) AS pay_month
FROM ${CLEAN_DB}.bank_transactions t
LEFT JOIN ${DW_DB}.dim_bank_account a
    ON t.bank = a.bank
   AND t.account = a.account
LEFT JOIN ${CLEAN_DB}.invoice_status st
    ON array_contains(st.tx_ids, t.tx_id)
LEFT JOIN ${CLEAN_DB}.invoices i
    ON st.invoice_id = i.invoice_id
LEFT JOIN ${DW_DB}.dim_project p
    ON i.project_code = p.project_code
LEFT JOIN ${CLEAN_DB}.suppliers cs
    ON t.counterparty_account = cs.bank_account
   AND t.counterparty_bank_code = cs.bank_code
LEFT JOIN ${DW_DB}.dim_supplier s
    ON cs.ico = s.ico
WHERE t.amount < 0;

-- Payment orders with invoice matching and clearing status
INSERT OVERWRITE TABLE ${DW_DB}.fact_payment_order
PARTITION (order_year)
SELECT
    o.order_id,
    COALESCE(a.account_key, -1) AS account_key,
    CAST(date_format(o.order_date, 'yyyyMMdd') AS INT) AS order_date_key,
    CAST(date_format(o.due_date, 'yyyyMMdd') AS INT) AS due_date_key,
    COALESCE(s.supplier_key, -1) AS supplier_key,
    st.invoice_id,
    COALESCE(p.project_key, -1) AS project_key,
    o.amount,
    CASE
        WHEN array_contains(st.uncleared_order_ids, o.order_id) THEN CAST(0 AS TINYINT)
        WHEN array_contains(st.order_ids, o.order_id) THEN CAST(1 AS TINYINT)
        ELSE CAST(NULL AS TINYINT)
    END AS cleared,
    YEAR(o.order_date) AS order_year
FROM ${CLEAN_DB}.payment_orders o
LEFT JOIN ${DW_DB}.dim_bank_account a
    ON o.bank = a.bank
   AND o.account = a.account
LEFT JOIN ${CLEAN_DB}.invoice_status st
    ON array_contains(st.order_ids, o.order_id)
    OR array_contains(st.uncleared_order_ids, o.order_id)
LEFT JOIN ${CLEAN_DB}.invoices i
    ON st.invoice_id = i.invoice_id
LEFT JOIN ${DW_DB}.dim_project p
    ON i.project_code = p.project_code
LEFT JOIN ${CLEAN_DB}.suppliers cs
    ON o.counterparty_account = cs.bank_account
   AND o.counterparty_bank_code = cs.bank_code
LEFT JOIN ${DW_DB}.dim_supplier s
    ON cs.ico = s.ico;

-- Payment orders with invoice matching and clearing status
